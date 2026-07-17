from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import queue
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump())
    if hasattr(value, "__dict__"):
        return _json_value(vars(value))
    return str(value)


async def _configure_cognee(root: Path, config: dict[str, Any]) -> None:
    import cognee
    from cognee.modules.engine.operations.setup import setup

    root.mkdir(parents=True, exist_ok=True)
    (root / "system" / "databases").mkdir(parents=True, exist_ok=True)
    cognee.config.data_root_directory(str(root))
    cognee.config.system_root_directory(str(root / "system"))
    llm = config.get("llm")
    embedding = config.get("embedding")
    if isinstance(llm, dict) and llm:
        cognee.config.set_llm_config(llm)
    if isinstance(embedding, dict) and embedding:
        cognee.config.set_embedding_config(embedding)
    await setup()


async def _remember_dataset(
    dataset_name: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    import cognee
    from cognee.tasks.ingestion.data_item import DataItem

    if any(dataset.name == dataset_name for dataset in await cognee.datasets.list_datasets()):
        raise FileExistsError(f"Knowledge dataset already exists: {dataset_name}")
    if not records:
        from cognee.modules.data.methods import create_authorized_dataset
        from cognee.modules.users.methods import get_default_user

        dataset = await create_authorized_dataset(dataset_name, await get_default_user())
        return {"dataset_id": str(dataset.id), "dataset_name": dataset.name}

    items = [
        DataItem(
            json.dumps(record, ensure_ascii=False, sort_keys=True),
            label=str(record["id"]),
            data_id=uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{dataset_name}:{record['id']}",
            ),
            external_metadata={
                "record_id": str(record["id"]),
                "kind": str(record["kind"]),
                "revision": str(record.get("revision") or ""),
            },
        )
        for record in records
    ]
    result = await cognee.remember(
        items,
        dataset_name=dataset_name,
        run_in_background=False,
    )
    return _json_value(result)


async def _read_dataset_records(dataset_name: str) -> list[dict[str, Any]]:
    import cognee
    from cognee.infrastructure.files.utils.open_data_file import open_data_file

    datasets = await cognee.datasets.list_datasets()
    dataset = next((item for item in datasets if item.name == dataset_name), None)
    if dataset is None:
        raise FileNotFoundError(f"Knowledge dataset not found: {dataset_name}")
    records: list[dict[str, Any]] = []
    for item in await cognee.datasets.list_data(dataset.id):
        async with open_data_file(item.raw_data_location) as source:
            records.append(json.loads(source.read().decode("utf-8")))
    return sorted(records, key=lambda record: str(record["id"]))


async def _handle_command(
    root: Path,
    command: dict[str, Any],
) -> Any:
    import cognee

    action = command["action"]
    if action == "health":
        return {"status": "ok"}
    if action == "remember":
        return await _remember_dataset(command["dataset_name"], command["records"])
    if action == "records":
        return await _read_dataset_records(command["dataset_name"])
    if action == "recall":
        result = await cognee.recall(
            query_text=command["query"],
            datasets=[command["dataset_name"]],
            top_k=command["top_k"],
            only_context=True,
            verbose=True,
        )
        return _json_value(result)
    if action == "forget":
        await cognee.forget(dataset=command["dataset_name"])
        return {"forgotten": command["dataset_name"]}
    if action == "shutdown":
        return {"shutdown": True}
    raise ValueError(f"Unknown memory command: {action}")


def project_memory_process(
    project_id: str,
    root_value: str,
    config: dict[str, Any],
    request_queue: multiprocessing.Queue,
    response_queue: multiprocessing.Queue,
) -> None:
    async def run() -> None:
        root = Path(root_value)
        await _configure_cognee(root, config)
        while True:
            command = await asyncio.to_thread(request_queue.get)
            request_id = command["request_id"]
            try:
                if (
                    command["action"] == "remember"
                    and command["records"]
                    and (not config.get("llm") or not config.get("embedding"))
                ):
                    raise RuntimeError(
                        "Cognee LLM and embedding models must be configured before storing knowledge"
                    )
                value = await _handle_command(root, command)
                response_queue.put({"request_id": request_id, "ok": True, "value": value})
            except Exception as exc:
                logger.exception(
                    "Cognee project command failed",
                    extra={"project_id": project_id, "action": command["action"]},
                )
                response_queue.put(
                    {
                        "request_id": request_id,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            if command["action"] == "shutdown":
                return

    asyncio.run(run())


@dataclass
class ProjectMemoryInstance:
    project_id: str
    process: multiprocessing.Process
    request_queue: multiprocessing.Queue
    response_queue: multiprocessing.Queue
    lock: asyncio.Lock
    config: dict[str, Any]

    async def request(self, action: str, **payload: Any) -> Any:
        async with self.lock:
            if not self.process.is_alive():
                raise RuntimeError(f"Cognee process for project {self.project_id} is not running")
            request_id = uuid.uuid4().hex
            self.request_queue.put(
                {
                    "request_id": request_id,
                    "action": action,
                    **payload,
                }
            )
            while True:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(self.response_queue.get, True, 1),
                        timeout=2,
                    )
                except (TimeoutError, queue.Empty):
                    if not self.process.is_alive():
                        raise RuntimeError(
                            f"Cognee process for project {self.project_id} stopped unexpectedly"
                        )
                    continue
                if response["request_id"] != request_id:
                    raise RuntimeError("Memory process returned an out-of-order response")
                if not response["ok"]:
                    raise RuntimeError(response["error"])
                return response["value"]


class MemorySupervisor:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.instances: dict[str, ProjectMemoryInstance] = {}
        self._lock = asyncio.Lock()
        self._context = multiprocessing.get_context("spawn")

    async def start(self, project_id: str, config: dict[str, Any]) -> ProjectMemoryInstance:
        async with self._lock:
            current = self.instances.get(project_id)
            if current and current.process.is_alive() and current.config == config:
                return current
            if current and current.process.is_alive():
                await current.request("shutdown")
                await asyncio.to_thread(current.process.join, 10)
            request_queue = self._context.Queue()
            response_queue = self._context.Queue()
            project_root = (self.root / project_id).resolve()
            project_root.relative_to(self.root)
            process = self._context.Process(
                target=project_memory_process,
                args=(
                    project_id,
                    str(project_root),
                    config,
                    request_queue,
                    response_queue,
                ),
                name=f"musegraph-cognee-{project_id[:8]}",
            )
            process.start()
            instance = ProjectMemoryInstance(
                project_id=project_id,
                process=process,
                request_queue=request_queue,
                response_queue=response_queue,
                lock=asyncio.Lock(),
                config=config,
            )
            self.instances[project_id] = instance
        await instance.request("health")
        return instance

    async def get(self, project_id: str) -> ProjectMemoryInstance:
        instance = self.instances.get(project_id)
        if instance is None or not instance.process.is_alive():
            raise LookupError(f"Cognee instance is not active for project {project_id}")
        return instance

    async def stop(self, project_id: str, *, delete_storage: bool = False) -> None:
        async with self._lock:
            instance = self.instances.pop(project_id, None)
        if instance and instance.process.is_alive():
            await instance.request("shutdown")
            await asyncio.to_thread(instance.process.join, 10)
        if delete_storage:
            project_root = (self.root / project_id).resolve()
            project_root.relative_to(self.root)
            if project_root.exists():
                shutil.rmtree(project_root)

    async def stop_all(self) -> None:
        instances = list(self.instances.values())
        for instance in instances:
            if instance.process.is_alive():
                await instance.request("shutdown")
                await asyncio.to_thread(instance.process.join, 10)
        self.instances.clear()

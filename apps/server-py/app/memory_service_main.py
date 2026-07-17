from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.services.memory_runtime import MemorySupervisor

supervisor = MemorySupervisor(Path(settings.COGNEE_DATA_DIR))


def require_internal_service(
    authorization: str = Header(default=""),
) -> None:
    if not settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service token is not configured",
        )
    if authorization != f"Bearer {settings.INTERNAL_SERVICE_TOKEN}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token")


class StartInstanceRequest(BaseModel):
    llm: dict[str, Any] = Field(default_factory=dict)
    embedding: dict[str, Any] = Field(default_factory=dict)


class RememberRequest(BaseModel):
    dataset_name: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,255}$")
    records: list[dict[str, Any]]


class RecallRequest(BaseModel):
    dataset_name: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,255}$")
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await supervisor.stop_all()


app = FastAPI(title="MuseGraph Memory Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "instances": len(supervisor.instances)}


@app.put("/internal/projects/{project_id}/instance", dependencies=[Depends(require_internal_service)])
async def start_instance(project_id: str, body: StartInstanceRequest):
    instance = await supervisor.start(project_id, body.model_dump())
    return {"project_id": project_id, "pid": instance.process.pid, "status": "ready"}


@app.get("/internal/projects/{project_id}/instance", dependencies=[Depends(require_internal_service)])
async def instance_health(project_id: str):
    instance = await supervisor.get(project_id)
    return await instance.request("health")


@app.delete("/internal/projects/{project_id}/instance", dependencies=[Depends(require_internal_service)])
async def delete_instance(project_id: str):
    await supervisor.stop(project_id, delete_storage=True)
    return {"project_id": project_id, "deleted": True}


@app.post("/internal/projects/{project_id}/remember", dependencies=[Depends(require_internal_service)])
async def remember(project_id: str, body: RememberRequest):
    instance = await supervisor.get(project_id)
    result = await instance.request(
        "remember",
        dataset_name=body.dataset_name,
        records=body.records,
    )
    return {"dataset_name": body.dataset_name, "result": result}


@app.get(
    "/internal/projects/{project_id}/datasets/{dataset_name}/records",
    dependencies=[Depends(require_internal_service)],
)
async def records(project_id: str, dataset_name: str):
    instance = await supervisor.get(project_id)
    return {"records": await instance.request("records", dataset_name=dataset_name)}


@app.post("/internal/projects/{project_id}/recall", dependencies=[Depends(require_internal_service)])
async def recall(project_id: str, body: RecallRequest):
    instance = await supervisor.get(project_id)
    result = await instance.request(
        "recall",
        dataset_name=body.dataset_name,
        query=body.query,
        top_k=body.top_k,
    )
    return {"results": result}


@app.delete(
    "/internal/projects/{project_id}/datasets/{dataset_name}",
    dependencies=[Depends(require_internal_service)],
)
async def forget(project_id: str, dataset_name: str):
    instance = await supervisor.get(project_id)
    return await instance.request("forget", dataset_name=dataset_name)

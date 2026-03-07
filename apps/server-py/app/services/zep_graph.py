import asyncio
import logging
import time
import uuid
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.project import TextProject

logger = logging.getLogger(__name__)

_ZEP_CHUNK_SIZE = 500
_ZEP_CHUNK_OVERLAP = 50
_ZEP_BATCH_SIZE = 3
_ZEP_WAIT_TIMEOUT_SECONDS = 600
_ZEP_WAIT_POLL_INTERVAL_SECONDS = 3.0


def _require_zep_api_key() -> str:
    api_key = str(settings.ZEP_API_KEY or "").strip()
    if api_key:
        return api_key
    raise RuntimeError("ZEP_API_KEY is not configured for the Zep Graphiti backend.")


def _build_graph_id() -> str:
    return f"musegraph_{uuid.uuid4().hex[:16]}"


def _split_text(text: str, *, chunk_size: int = _ZEP_CHUNK_SIZE, overlap: int = _ZEP_CHUNK_OVERLAP) -> list[str]:
    source = str(text or "").strip()
    if not source:
        return []
    if len(source) <= chunk_size:
        return [source]

    chunks: list[str] = []
    cursor = 0
    total_length = len(source)
    while cursor < total_length:
        end = min(cursor + chunk_size, total_length)
        if end < total_length:
            boundary = source.rfind("\n\n", cursor + max(1, int(chunk_size * 0.6)), end)
            if boundary > cursor:
                end = boundary
        piece = source[cursor:end].strip()
        if piece:
            chunks.append(piece)
        if end >= total_length:
            break
        next_cursor = max(end - overlap, cursor + 1)
        if next_cursor <= cursor:
            next_cursor = end
        cursor = next_cursor
    return chunks or [source]


async def _load_project(project_id: str, db: AsyncSession | None) -> TextProject | None:
    if db is None:
        return None
    result = await db.execute(select(TextProject).where(TextProject.id == project_id))
    return result.scalar_one_or_none()


def _import_zep_runtime() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    try:
        from pydantic import Field
        from zep_cloud import EpisodeData, EntityEdgeSourceTarget
        from zep_cloud.client import Zep
        from zep_cloud.external_clients.ontology import EdgeModel, EntityModel, EntityText
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Zep graph backend dependency is missing. Install `zep-cloud` and rebuild the server."
        ) from exc
    return Zep, EpisodeData, EntityEdgeSourceTarget, EdgeModel, EntityModel, EntityText, Field


def _create_zep_client() -> Any:
    Zep, *_ = _import_zep_runtime()
    return Zep(api_key=_require_zep_api_key())


def _set_ontology_sync(client: Any, graph_id: str, ontology: dict[str, Any] | None) -> None:
    if not isinstance(ontology, dict):
        return

    _, _, EntityEdgeSourceTarget, EdgeModel, EntityModel, EntityText, Field = _import_zep_runtime()

    reserved_names = {"uuid", "name", "group_id", "name_embedding", "summary", "created_at"}

    def safe_attr_name(attr_name: str) -> str:
        normalized = str(attr_name or "").strip() or "attribute"
        if normalized.lower() in reserved_names:
            return f"entity_{normalized}"
        return normalized

    entity_types: dict[str, Any] = {}
    for entity_def in ontology.get("entity_types", []) or []:
        name = str(entity_def.get("name") or "").strip()
        if not name:
            continue
        description = str(entity_def.get("description") or f"A {name} entity.").strip()
        attrs: dict[str, Any] = {"__doc__": description}
        annotations: dict[str, Any] = {}
        for attr_def in entity_def.get("attributes", []) or []:
            attr_name = safe_attr_name(str(attr_def.get("name") or "").strip())
            attr_desc = str(attr_def.get("description") or attr_name).strip()
            attrs[attr_name] = Field(description=attr_desc, default=None)
            annotations[attr_name] = EntityText | None
        attrs["__annotations__"] = annotations
        entity_types[name] = type(name, (EntityModel,), attrs)

    edge_definitions: dict[str, Any] = {}
    for edge_def in ontology.get("edge_types", []) or []:
        name = str(edge_def.get("name") or "").strip()
        if not name:
            continue
        description = str(edge_def.get("description") or f"A {name} relationship.").strip()
        attrs = {"__doc__": description}
        annotations: dict[str, Any] = {}
        for attr_def in edge_def.get("attributes", []) or []:
            attr_name = safe_attr_name(str(attr_def.get("name") or "").strip())
            attr_desc = str(attr_def.get("description") or attr_name).strip()
            attrs[attr_name] = Field(description=attr_desc, default=None)
            annotations[attr_name] = str | None
        attrs["__annotations__"] = annotations
        class_name = "".join(part.capitalize() for part in name.split("_")) or "Relation"
        edge_class = type(class_name, (EdgeModel,), attrs)
        source_targets = []
        for pair in edge_def.get("source_targets", []) or []:
            source_targets.append(
                EntityEdgeSourceTarget(
                    source=str(pair.get("source") or "Entity"),
                    target=str(pair.get("target") or "Entity"),
                )
            )
        if source_targets:
            edge_definitions[name] = (edge_class, source_targets)

    if entity_types or edge_definitions:
        client.graph.set_ontology(
            graph_ids=[graph_id],
            entities=entity_types or None,
            edges=edge_definitions or None,
        )


def _batch_add_episodes_sync(
    client: Any,
    graph_id: str,
    chunks: list[str],
    *,
    progress_callback: Callable[[int, str], None] | None = None,
) -> list[str]:
    _, EpisodeData, *_ = _import_zep_runtime()
    episode_ids: list[str] = []
    total_chunks = len(chunks)
    total_batches = max(1, (total_chunks + _ZEP_BATCH_SIZE - 1) // _ZEP_BATCH_SIZE)

    for offset in range(0, total_chunks, _ZEP_BATCH_SIZE):
        batch = chunks[offset:offset + _ZEP_BATCH_SIZE]
        batch_index = (offset // _ZEP_BATCH_SIZE) + 1
        episodes = [EpisodeData(data=chunk, type="text") for chunk in batch]
        result = client.graph.add_batch(graph_id=graph_id, episodes=episodes)
        if isinstance(result, list):
            for item in result:
                episode_id = getattr(item, "uuid_", None) or getattr(item, "uuid", None)
                if episode_id:
                    episode_ids.append(str(episode_id))
        if progress_callback:
            progress = 45 + int((batch_index / total_batches) * 25)
            progress_callback(progress, f"Uploading graph batches {batch_index}/{total_batches}...")
        time.sleep(0.5)

    return episode_ids


def _wait_for_episodes_sync(
    client: Any,
    episode_ids: list[str],
    *,
    progress_callback: Callable[[int, str], None] | None = None,
    timeout_seconds: int = _ZEP_WAIT_TIMEOUT_SECONDS,
) -> None:
    if not episode_ids:
        return

    pending = set(episode_ids)
    completed = 0
    started_at = time.time()
    total = len(episode_ids)

    while pending:
        elapsed = time.time() - started_at
        if elapsed > timeout_seconds:
            raise RuntimeError(
                f"Zep episode processing timed out after {timeout_seconds}s ({completed}/{total} completed)."
            )
        for episode_id in list(pending):
            try:
                episode = client.graph.episode.get(uuid_=episode_id)
            except Exception:
                continue
            if bool(getattr(episode, "processed", False)):
                pending.remove(episode_id)
                completed += 1
        if progress_callback:
            ratio = completed / total if total else 1.0
            progress_callback(
                72 + int(ratio * 16),
                f"Graphiti is processing episodes... {completed}/{total} complete ({int(elapsed)}s elapsed)",
            )
        if pending:
            time.sleep(_ZEP_WAIT_POLL_INTERVAL_SECONDS)


async def build_graph(
    project_id: str,
    text: str,
    *,
    ontology: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> str:
    chunks = _split_text(text)
    if not chunks:
        raise ValueError("No graph input text provided")

    project = await _load_project(project_id, db)
    existing_graph_id = str(getattr(project, "cognee_dataset_id", "") or "").strip() if project is not None else ""
    graph_id = existing_graph_id or _build_graph_id()
    graph_name = str(getattr(project, "title", "") or "MuseGraph Graph").strip() or "MuseGraph Graph"
    client = _create_zep_client()

    def emit(progress: int, message: str) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(progress, message)
        except Exception:
            pass

    if not existing_graph_id:
        emit(30, "Creating Graphiti graph...")
        await asyncio.to_thread(
            client.graph.create,
            graph_id=graph_id,
            name=graph_name,
            description="MuseGraph knowledge graph powered by Zep Graphiti",
        )
    else:
        emit(30, "Reusing existing Graphiti graph...")

    if isinstance(ontology, dict) and ontology:
        emit(38, "Setting graph ontology...")
        await asyncio.to_thread(_set_ontology_sync, client, graph_id, ontology)

    emit(45, "Uploading graph episodes...")
    episode_ids = await asyncio.to_thread(
        _batch_add_episodes_sync,
        client,
        graph_id,
        chunks,
        progress_callback=emit,
    )

    emit(72, "Waiting for Graphiti indexing...")
    await asyncio.to_thread(
        _wait_for_episodes_sync,
        client,
        episode_ids,
        progress_callback=emit,
    )
    emit(100, "Graph build complete")
    return graph_id


async def search_graph(
    project_id: str,
    query: str,
    *,
    top_k: int = 10,
    search_type: str = "INSIGHTS",
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    project = await _load_project(project_id, db)
    graph_id = str(getattr(project, "cognee_dataset_id", "") or "").strip() if project is not None else ""
    if not graph_id:
        raise RuntimeError(f"Project {project_id} does not have a graph id.")

    normalized_type = str(search_type or "").strip().upper()
    scope = "edges" if normalized_type not in {"SUMMARIES", "CHUNKS"} else "nodes"
    client = _create_zep_client()
    result = await asyncio.to_thread(
        client.graph.search,
        graph_id=graph_id,
        query=query,
        limit=max(1, min(50, int(top_k or 10))),
        scope=scope,
        reranker="cross_encoder",
    )

    items: list[dict[str, Any]] = []
    for edge in getattr(result, "edges", None) or []:
        fact = str(getattr(edge, "fact", "") or "").strip()
        if not fact:
            continue
        items.append(
            {
                "id": str(getattr(edge, "uuid_", None) or getattr(edge, "uuid", "") or ""),
                "content": fact,
                "type": str(getattr(edge, "name", "") or "Edge"),
                "score": float(getattr(edge, "score", 1.0) or 1.0),
            }
        )
    for node in getattr(result, "nodes", None) or []:
        summary = str(getattr(node, "summary", "") or getattr(node, "name", "") or "").strip()
        if not summary:
            continue
        labels = getattr(node, "labels", None) or []
        node_type = next((str(label) for label in labels if str(label) not in {"Entity", "Node"}), "Entity")
        items.append(
            {
                "id": str(getattr(node, "uuid_", None) or getattr(node, "uuid", "") or ""),
                "content": summary,
                "type": node_type,
                "score": float(getattr(node, "score", 1.0) or 1.0),
            }
        )
    return items


async def get_graph_visualization(project_id: str, *, db: AsyncSession | None = None) -> dict[str, Any]:
    project = await _load_project(project_id, db)
    graph_id = str(getattr(project, "cognee_dataset_id", "") or "").strip() if project is not None else ""
    if not graph_id:
        return {"nodes": [], "edges": []}

    client = _create_zep_client()
    nodes = await asyncio.to_thread(client.graph.node.get_by_graph_id, graph_id=graph_id)
    edges = await asyncio.to_thread(client.graph.edge.get_by_graph_id, graph_id=graph_id)

    node_map: dict[str, str] = {}
    node_payload: list[dict[str, Any]] = []
    for node in nodes or []:
        node_id = str(getattr(node, "uuid_", None) or getattr(node, "uuid", "") or "")
        if not node_id:
            continue
        labels = list(getattr(node, "labels", None) or [])
        node_type = next((str(label) for label in labels if str(label) not in {"Entity", "Node"}), "Entity")
        label = str(getattr(node, "name", "") or node_id)
        node_map[node_id] = label
        node_payload.append(
            {
                "id": node_id,
                "label": label,
                "type": node_type,
                "summary": str(getattr(node, "summary", "") or ""),
                "attributes": getattr(node, "attributes", None) or {},
            }
        )

    edge_payload: list[dict[str, Any]] = []
    for edge in edges or []:
        edge_id = str(getattr(edge, "uuid_", None) or getattr(edge, "uuid", "") or "")
        source = str(getattr(edge, "source_node_uuid", "") or "")
        target = str(getattr(edge, "target_node_uuid", "") or "")
        if not source or not target:
            continue
        label = str(getattr(edge, "name", "") or getattr(edge, "fact_type", "") or "RELATED")
        edge_payload.append(
            {
                "id": edge_id or f"{source}:{target}:{label}",
                "source": source,
                "target": target,
                "label": label,
                "type": label,
                "fact": str(getattr(edge, "fact", "") or ""),
                "source_label": node_map.get(source, source),
                "target_label": node_map.get(target, target),
                "attributes": getattr(edge, "attributes", None) or {},
            }
        )

    return {"nodes": node_payload, "edges": edge_payload}


async def delete_graph(project_id: str, *, db: AsyncSession | None = None) -> None:
    project = await _load_project(project_id, db)
    graph_id = str(getattr(project, "cognee_dataset_id", "") or "").strip() if project is not None else ""
    if not graph_id:
        return
    client = _create_zep_client()
    await asyncio.to_thread(client.graph.delete, graph_id=graph_id)

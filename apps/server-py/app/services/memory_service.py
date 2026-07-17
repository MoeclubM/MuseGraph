from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import app.services.memory_backend as memory_backend


async def close_memory_runtime() -> None:
    await memory_backend.close_runtime()


async def build_memory(
    project_id: str,
    text: str,
    *,
    ontology: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
    progress_callback: Any | None = None,
    model: str | None = None,
    embedding_model: str | None = None,
    memory_id_override: str | None = None,
    reset: bool = True,
    operation_id: str | None = None,
) -> str:
    return await memory_backend.ingest_project(
        project_id,
        text,
        ontology=ontology,
        db=db,
        progress_callback=progress_callback,
        model=model,
        embedding_model=embedding_model,
        memory_id_override=memory_id_override,
        reset=reset,
        operation_id=operation_id,
    )


async def delete_memory(
    project_id: str,
    *,
    model: str | None = None,
    embedding_model: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    _ = model
    await memory_backend.delete_project(project_id, db=db, embedding_model=embedding_model)


async def search_memory(
    project_id: str,
    query: str,
    search_type: str = "INSIGHTS",
    top_k: int = 10,
    *,
    db: AsyncSession | None = None,
    operation_id: str | None = None,
) -> list[dict[str, Any]]:
    _ = search_type
    return await memory_backend.search(project_id, query, top_k=top_k, db=db, operation_id=operation_id)


async def get_memory_visualization(
    project_id: str,
    *,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    data = await memory_backend.export_project(project_id, db=db)
    return {"nodes": data["nodes"], "edges": data["edges"]}


async def get_memory_visualization_for_group(
    project_id: str,
    *,
    memory_id: str,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    data = await memory_backend.export_project(project_id, db=db, memory_id=memory_id)
    return {"nodes": data["nodes"], "edges": data["edges"]}


async def has_memory_data(project_id: str, *, db: AsyncSession | None = None) -> bool:
    return await memory_backend.has_project(project_id, db=db)


async def memory_rag_query(
    project_id: str,
    query: str,
    *,
    top_k: int = 6,
    neighbor_depth: int = 1,
    db: AsyncSession | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    rows = await memory_backend.search(project_id, query, top_k=top_k, db=db, operation_id=operation_id)
    if rows and neighbor_depth > 0:
        graph = await memory_backend.export_project(project_id, db=db)
    else:
        # No hits (or no expansion requested): skip the costly full graph export.
        graph = {"nodes": [], "edges": []}
    graph_nodes = graph.get("nodes")
    graph_edges = graph.get("edges")
    if not isinstance(graph_nodes, list):
        raise TypeError("Memory export returned non-list nodes")
    if not isinstance(graph_edges, list):
        raise TypeError("Memory export returned non-list edges")

    nodes = [
        {
            "id": row.get("id") or f"memory-{index}",
            "label": str(row.get("content") or "")[:120],
            "type": row.get("type") or "memory",
            "content": row.get("content") or "",
            "score": row.get("score"),
        }
        for index, row in enumerate(rows, start=1)
    ]
    node_by_id = {
        str(node.get("id") or ""): node
        for node in graph_nodes
        if isinstance(node, dict) and str(node.get("id") or "").strip()
    }
    selected_ids = {str(node["id"]) for node in nodes if str(node.get("id") or "").strip()}
    expanded_ids = set(selected_ids)
    selected_edges: list[dict[str, Any]] = []
    max_depth = max(0, int(neighbor_depth or 0))
    frontier = set(selected_ids)
    for _depth in range(max_depth):
        next_frontier: set[str] = set()
        for edge in graph_edges:
            if not isinstance(edge, dict):
                raise TypeError("Memory export edge row is not an object")
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            if not source or not target:
                raise TypeError("Memory export edge is missing source or target")
            if source not in frontier and target not in frontier:
                continue
            selected_edges.append(edge)
            for node_id in (source, target):
                if node_id not in expanded_ids:
                    expanded_ids.add(node_id)
                    next_frontier.add(node_id)
        frontier = next_frontier
        if not frontier:
            break

    seen_node_ids = {str(node["id"]) for node in nodes}
    for node_id in sorted(expanded_ids - seen_node_ids):
        graph_node = node_by_id.get(node_id)
        if not graph_node:
            continue
        nodes.append({
            "id": node_id,
            "label": str(graph_node.get("label") or graph_node.get("content") or node_id)[:120],
            "type": graph_node.get("type") or "memory",
            "content": graph_node.get("content") or "",
            "score": None,
            "properties": graph_node.get("properties") if isinstance(graph_node.get("properties"), dict) else {},
        })

    edge_ids: set[str] = set()
    relationships: list[dict[str, Any]] = []
    for index, edge in enumerate(selected_edges, start=1):
        edge_id = str(edge.get("id") or f"edge-{index}")
        if edge_id in edge_ids:
            continue
        edge_ids.add(edge_id)
        relationships.append({
            "id": edge_id,
            "source": edge.get("source"),
            "target": edge.get("target"),
            "type": edge.get("type") or edge.get("label") or "RELATED_TO",
            "label": edge.get("label") or edge.get("type") or "related",
            "weight": edge.get("weight"),
            "properties": edge.get("properties") if isinstance(edge.get("properties"), dict) else {},
        })

    context_text = "\n".join(
        f"[{row.get('type') or 'memory'} score={row.get('score')}] {row.get('content')}"
        for row in rows
    )
    return {
        "entities": nodes,
        "relationships": relationships,
        "context_text": context_text,
        "submemory": {"nodes": nodes, "edges": relationships},
    }


async def writeback_agent_to_memory(
    project_id: str,
    payload: dict[str, Any],
    *,
    operation_id: str | None = None,
    operation_type: str | None = None,
    source_text: str | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    return await memory_backend.writeback_agent(
        project_id,
        payload,
        operation_id=operation_id,
        operation_type=operation_type,
        source_text=source_text,
        db=db,
    )


async def export_memory_data(
    project_id: str,
    *,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    return await memory_backend.export_project(project_id, db=db)


async def query_memory_timeline(
    project_id: str,
    *,
    at_timestamp: str | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    data = await memory_backend.export_project(project_id, db=db)
    return {
        "at": at_timestamp,
        "from": from_timestamp,
        "to": to_timestamp,
        "nodes": data["nodes"],
        "edges": data["edges"],
    }

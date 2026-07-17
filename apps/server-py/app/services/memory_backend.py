from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import TextProject
from app.services.cognee_backend import (
    build_project_memory,
    close_memory_runtime,
    delete_project_memory,
    export_project_memory,
    has_project_memory,
    retrieve_creative_memory,
    search_project_memory,
    writeback_agent_memory,
)


async def close_runtime() -> None:
    await close_memory_runtime()


async def ingest_project(
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
    return await build_project_memory(
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


async def retrieve(
    *,
    project_id: str,
    project: TextProject,
    query_plan: list[dict[str, Any]],
    context_query: str,
    db: AsyncSession,
) -> dict[str, Any]:
    return await retrieve_creative_memory(
        project_id=project_id,
        project=project,
        query_plan=query_plan,
        context_query=context_query,
        db=db,
    )


async def search(
    project_id: str,
    query: str,
    *,
    top_k: int = 10,
    db: AsyncSession | None = None,
    project: TextProject | None = None,
    operation_id: str | None = None,
) -> list[dict[str, Any]]:
    return await search_project_memory(project_id, query, top_k=top_k, db=db, project=project, operation_id=operation_id)


async def delete_project(project_id: str, *, db: AsyncSession | None = None, embedding_model: str | None = None) -> dict[str, Any]:
    return await delete_project_memory(project_id, db=db, embedding_model=embedding_model)


async def has_project(project_id: str, *, db: AsyncSession | None = None, project: TextProject | None = None) -> bool:
    return await has_project_memory(project_id, db=db, project=project)


async def export_project(
    project_id: str,
    *,
    db: AsyncSession | None = None,
    project: TextProject | None = None,
    memory_id: str | None = None,
) -> dict[str, Any]:
    return await export_project_memory(project_id, db=db, project=project, memory_id_override=memory_id)


async def writeback_agent(
    project_id: str,
    payload: dict[str, Any],
    *,
    operation_id: str | None = None,
    operation_type: str | None = None,
    source_text: str | None = None,
    db: AsyncSession | None = None,
    project: TextProject | None = None,
    llm_model_override: str | None = None,
    embedding_model_override: str | None = None,
) -> dict[str, Any]:
    return await writeback_agent_memory(
        project_id,
        payload,
        operation_id=operation_id,
        operation_type=operation_type,
        source_text=source_text,
        db=db,
        project=project,
        llm_model_override=llm_model_override,
        embedding_model_override=embedding_model_override,
    )

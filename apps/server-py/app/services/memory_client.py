from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


def _headers() -> dict[str, str]:
    if not settings.INTERNAL_SERVICE_TOKEN:
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is required")
    return {"Authorization": f"Bearer {settings.INTERNAL_SERVICE_TOKEN}"}


async def start_project_memory_instance(
    project_id: str,
    *,
    llm: dict[str, Any],
    embedding: dict[str, Any],
) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=settings.MEMORY_SERVICE_URL, timeout=60) as client:
        response = await client.put(
            f"/internal/projects/{project_id}/instance",
            headers=_headers(),
            json={"llm": llm, "embedding": embedding},
        )
        response.raise_for_status()
        return response.json()


async def remember_knowledge_dataset(
    project_id: str,
    dataset_name: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    async with httpx.AsyncClient(
        base_url=settings.MEMORY_SERVICE_URL,
        timeout=None,
    ) as client:
        response = await client.post(
            f"/internal/projects/{project_id}/remember",
            headers=_headers(),
            json={"dataset_name": dataset_name, "records": records},
        )
        response.raise_for_status()
        return response.json()


async def delete_project_memory_instance(project_id: str) -> None:
    async with httpx.AsyncClient(base_url=settings.MEMORY_SERVICE_URL, timeout=60) as client:
        response = await client.delete(
            f"/internal/projects/{project_id}/instance",
            headers=_headers(),
        )
        response.raise_for_status()


async def list_knowledge_records(project_id: str, dataset_name: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(base_url=settings.MEMORY_SERVICE_URL, timeout=60) as client:
        response = await client.get(
            f"/internal/projects/{project_id}/datasets/{dataset_name}/records",
            headers=_headers(),
        )
        response.raise_for_status()
        return list(response.json()["records"])


async def forget_knowledge_dataset(project_id: str, dataset_name: str) -> None:
    async with httpx.AsyncClient(base_url=settings.MEMORY_SERVICE_URL, timeout=60) as client:
        response = await client.delete(
            f"/internal/projects/{project_id}/datasets/{dataset_name}",
            headers=_headers(),
        )
        response.raise_for_status()


async def recall_knowledge(
    project_id: str,
    dataset_name: str,
    query: str,
    *,
    top_k: int = 10,
) -> list[Any]:
    async with httpx.AsyncClient(
        base_url=settings.MEMORY_SERVICE_URL,
        timeout=None,
    ) as client:
        response = await client.post(
            f"/internal/projects/{project_id}/recall",
            headers=_headers(),
            json={"dataset_name": dataset_name, "query": query, "top_k": top_k},
        )
        response.raise_for_status()
        return list(response.json()["results"])

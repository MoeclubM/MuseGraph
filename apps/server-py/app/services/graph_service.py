from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.ai import call_llm
from app.services.graphiti_graph import (
    GraphBuildPartialFailure,
    build_graph as build_graph_with_graphiti,
    delete_graph as delete_graph_with_graphiti,
    get_graph_visualization_for_group as get_graph_visualization_for_group_with_graphiti,
    get_graph_visualization as get_graph_visualization_with_graphiti,
    has_graph_data as has_graphiti_graph_data,
    search_graph as search_graph_with_graphiti,
    setup_graphiti,
)
from app.services.llm_json import StrictJsonSchemaModel, extract_json_object


class RerankedCandidate(StrictJsonSchemaModel):
    id: int
    score: float


class RerankResponse(StrictJsonSchemaModel):
    ranked: list[RerankedCandidate]


def _ensure_supported_graph_backend() -> None:
    backend = str(getattr(settings, "GRAPH_BACKEND", "graphiti") or "graphiti").strip().lower() or "graphiti"
    if backend != "graphiti":
        raise RuntimeError(f"Unsupported graph backend '{backend}'. Only local Graphiti is supported.")


def _short_text(value: Any, *, limit: int = 90) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\[ONTOLOGY_CONTEXT\][\s\S]*?\[/ONTOLOGY_CONTEXT\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)] + "..."


def _tokenize_text_for_relevance(text: str) -> set[str]:
    source = str(text or "").lower()
    if not source:
        return set()
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", source)
    latin_words = re.findall(r"[a-z0-9_]+", source)
    return {token for token in (cjk_chars + latin_words) if token}


def _lexical_relevance_score(query: str, content: str) -> float:
    query_tokens = _tokenize_text_for_relevance(query)
    content_tokens = _tokenize_text_for_relevance(content)
    if not query_tokens or not content_tokens:
        return 0.0
    overlap_ratio = len(query_tokens & content_tokens) / max(1, len(query_tokens))
    phrase_bonus = 0.0
    normalized_query = str(query or "").strip().lower()
    if normalized_query and normalized_query in str(content or "").lower():
        phrase_bonus = 0.12
    return max(0.0, min(1.0, overlap_ratio + phrase_bonus))


def _rerank_search_results_lexical(
    query: str,
    results: list[dict[str, Any]],
    *,
    top_n: int,
) -> list[dict[str, Any]]:
    if not results:
        return []
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for idx, item in enumerate(results):
        content = str(item.get("content") or "")
        score = _lexical_relevance_score(query, content)
        enriched = dict(item)
        enriched["reranker_score"] = round(float(score), 6)
        enriched["reranker_source"] = "lexical_fallback"
        scored.append((score, idx, enriched))
    scored.sort(key=lambda row: (row[0], -row[1]), reverse=True)
    limit = max(1, min(int(top_n), len(scored)))
    return [row[2] for row in scored[:limit]]


def _build_reranker_prompt(query: str, candidates: list[dict[str, Any]]) -> str:
    return (
        "You are a retrieval reranker for RAG.\n"
        "Given a user query and candidate passages, use the provided response schema.\n"
        "Rules:\n"
        "1) Keep only ids from provided candidates.\n"
        "2) score must be in [0, 1], sorted descending by relevance.\n"
        "3) Prefer factual grounding, temporal consistency, and direct answerability.\n"
        "4) Do not add explanations.\n\n"
        f"Query:\n{str(query or '').strip()}\n\n"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=False)}"
    )


async def _rerank_search_results_with_llm(
    query: str,
    results: list[dict[str, Any]],
    *,
    db: AsyncSession,
    model: str,
    top_n: int,
) -> list[dict[str, Any]]:
    if not results:
        return []
    selected_model = str(model or "").strip()
    if not selected_model:
        return _rerank_search_results_lexical(query, results, top_n=top_n)

    limit = max(1, min(int(top_n), len(results)))
    candidates: list[dict[str, Any]] = []
    for idx, item in enumerate(results, start=1):
        candidates.append(
            {
                "id": idx,
                "content": _short_text(item.get("content"), limit=1000),
            }
        )

    llm_result = await call_llm(
        selected_model,
        _build_reranker_prompt(query, candidates),
        db,
        max_tokens=900,
        prefer_stream_override=False,
        stream_fallback_nonstream_override=False,
        response_schema=RerankResponse,
    )
    payload = extract_json_object(str(llm_result.get("content") or "")) or {}
    ranked_raw = payload.get("ranked") if isinstance(payload, dict) else None
    if not isinstance(ranked_raw, list):
        return _rerank_search_results_lexical(query, results, top_n=limit)

    scored_rows: list[tuple[float, int, dict[str, Any]]] = []
    seen_ids: set[int] = set()
    for position, row in enumerate(ranked_raw):
        row_id: int | None = None
        row_score: float | None = None
        if isinstance(row, dict):
            try:
                row_id = int(row.get("id"))
            except Exception:
                row_id = None
            try:
                row_score = float(row.get("score"))
            except Exception:
                row_score = None
        else:
            try:
                row_id = int(row)
            except Exception:
                row_id = None

        if row_id is None or row_id < 1 or row_id > len(results) or row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        if row_score is None:
            row_score = 1.0 - (position / max(1, len(results)))
        bounded_score = max(0.0, min(1.0, float(row_score)))
        enriched = dict(results[row_id - 1])
        enriched["reranker_score"] = round(bounded_score, 6)
        enriched["reranker_source"] = "llm"
        scored_rows.append((bounded_score, row_id - 1, enriched))

    if not scored_rows:
        return _rerank_search_results_lexical(query, results, top_n=limit)

    for idx, item in enumerate(results):
        if idx + 1 in seen_ids:
            continue
        fallback_score = _lexical_relevance_score(query, str(item.get("content") or ""))
        enriched = dict(item)
        enriched["reranker_score"] = round(float(fallback_score), 6)
        enriched["reranker_source"] = "llm+fallback"
        scored_rows.append((fallback_score, idx, enriched))

    scored_rows.sort(key=lambda row: (row[0], -row[1]), reverse=True)
    return [row[2] for row in scored_rows[:limit]]


async def setup_graph_runtime() -> None:
    _ensure_supported_graph_backend()
    await setup_graphiti()


async def build_graph(
    project_id: str,
    text: str,
    *,
    ontology: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
    progress_callback: Any | None = None,
    model: str | None = None,
    embedding_model: str | None = None,
    graph_id_override: str | None = None,
    chunk_indices: list[int] | None = None,
    continue_on_error: bool = False,
) -> str:
    _ensure_supported_graph_backend()
    return await build_graph_with_graphiti(
        project_id,
        text,
        ontology=ontology,
        db=db,
        progress_callback=progress_callback,
        model=model,
        embedding_model=embedding_model,
        graph_id_override=graph_id_override,
        chunk_indices=chunk_indices,
        continue_on_error=continue_on_error,
    )


async def delete_graph(
    project_id: str,
    *,
    model: str | None = None,
    embedding_model: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    _ensure_supported_graph_backend()
    await delete_graph_with_graphiti(
        project_id,
        model=model,
        embedding_model=embedding_model,
        db=db,
    )


async def search_graph(
    project_id: str,
    query: str,
    search_type: str = "INSIGHTS",
    top_k: int = 10,
    *,
    db: AsyncSession | None = None,
    use_reranker: bool = False,
    reranker_model: str | None = None,
    reranker_top_n: int | None = None,
) -> list[dict[str, Any]]:
    _ensure_supported_graph_backend()
    parsed = await search_graph_with_graphiti(
        project_id,
        query,
        top_k=top_k,
        search_type=str(search_type or "").strip().upper() or "INSIGHTS",
        db=db,
    )
    if not use_reranker:
        return parsed

    limit = int(reranker_top_n or top_k or len(parsed) or 1)
    limit = max(1, min(50, limit))
    if db is not None and str(reranker_model or "").strip():
        try:
            return await _rerank_search_results_with_llm(
                query,
                parsed,
                db=db,
                model=str(reranker_model or "").strip(),
                top_n=limit,
            )
        except Exception:
            pass
    return _rerank_search_results_lexical(query, parsed, top_n=limit)


async def get_graph_visualization(
    project_id: str,
    *,
    db: AsyncSession | None = None,
    alias_model: str | None = None,
) -> dict[str, Any]:
    _ensure_supported_graph_backend()
    _ = alias_model
    return await get_graph_visualization_with_graphiti(project_id, db=db)


async def get_graph_visualization_for_group(
    project_id: str,
    *,
    graph_id: str,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    _ensure_supported_graph_backend()
    return await get_graph_visualization_for_group_with_graphiti(project_id, graph_id=graph_id, db=db)


async def has_graph_data(project_id: str, *, db: AsyncSession | None = None) -> bool:
    _ensure_supported_graph_backend()
    return await has_graphiti_graph_data(project_id, db=db)

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import AIProviderConfig
from app.models.project import TextOperation, TextProject
from app.services.provider_models import get_provider_chat_models, get_provider_embedding_models

logger = logging.getLogger(__name__)

_COGNEE_INGEST_TIMEOUT = float(settings.COGNEE_INGEST_TIMEOUT_SECONDS)

_cognee_initialized = False
_cognee_init_lock = asyncio.Lock()


async def _ensure_cognee_initialized() -> None:
    global _cognee_initialized
    if _cognee_initialized:
        return
    async with _cognee_init_lock:
        if _cognee_initialized:
            return
        import cognee
        import litellm
        from pathlib import Path as _Path
        # vLLM / Qwen 兼容端点不接受 OpenAI text-embedding-3 的 dimensions 限制；显式声明 litellm 丢弃不支持参数。
        litellm.drop_params = True
        # cognee 1.2.1: data_root_directory / system_root_directory 是 staticmethod，必须调用而非赋值。
        cognee_root = _Path(settings.COGNEE_DATA_DIR).resolve()
        cognee_root.mkdir(parents=True, exist_ok=True)
        cognee.config.data_root_directory(str(cognee_root))
        cognee.config.system_root_directory(str(cognee_root / "system"))
        _cognee_initialized = True


def _provider_models(provider: AIProviderConfig, kind: str) -> list[str]:
    if kind == "embedding":
        return get_provider_embedding_models(provider)
    return get_provider_chat_models(provider)


async def _resolve_provider_for_model(
    db: AsyncSession | None,
    *,
    model: str | None,
    kind: str,
) -> tuple[AIProviderConfig | None, str]:
    selected_model = str(model or "").strip()
    if not selected_model:
        raise RuntimeError(f"Cognee {kind} model is required; configure the project component model explicitly.")
    if db is None:
        raise RuntimeError(f"Cognee {kind} provider resolution requires a database session.")
    result = await db.execute(
        select(AIProviderConfig)
        .where(AIProviderConfig.is_active == True)
        .order_by(AIProviderConfig.priority.desc(), AIProviderConfig.created_at.asc())
    )
    providers = result.scalars().all()
    for provider in providers:
        if selected_model in _provider_models(provider, kind):
            return provider, selected_model
    raise RuntimeError(f'Cognee {kind} model "{selected_model}" is not registered in any active provider.')


def _require_openai_compatible(provider: AIProviderConfig, *, component: str) -> None:
    provider_type = str(provider.provider or "").strip().lower()
    if provider_type != "openai_compatible":
        raise RuntimeError(
            f"Cognee {component} requires an OpenAI-compatible provider; "
            f'provider "{provider.name}" is configured as "{provider.provider}".'
        )


def _memory_user_id(project_id: str) -> str:
    return f"project:{str(project_id or '').strip()}"


async def _load_project(project_id: str, db: AsyncSession | None) -> TextProject | None:
    if db is None:
        return None
    result = await db.execute(select(TextProject).where(TextProject.id == project_id))
    return result.scalar_one_or_none()


def _project_memory_id(project: TextProject | None) -> str:
    return str(getattr(project, "memory_id", "") or "").strip()


async def _configure_cognee(
    *,
    llm_provider: AIProviderConfig | None,
    llm_model: str,
    embedding_provider: AIProviderConfig | None,
    embedding_model: str,
) -> None:
    import cognee

    if llm_provider is not None:
        _require_openai_compatible(llm_provider, component="LLM")
        cognee.config.set_llm_config({
            "llm_provider": "openai",
            "llm_model": f"openai/{llm_model}" if not llm_model.startswith("openai/") else llm_model,
            "llm_endpoint": llm_provider.base_url or "",
            "llm_api_key": llm_provider.api_key,
            "llm_max_completion_tokens": settings.COGNEE_LLM_MAX_TOKENS,
        })

    if embedding_provider is not None:
        _require_openai_compatible(embedding_provider, component="embedding")
        cognee.config.set_embedding_config({
            "embedding_provider": "huggingface",
            "embedding_model": f"openai/{embedding_model}" if not embedding_model.startswith("openai/") else embedding_model,
            "embedding_endpoint": embedding_provider.base_url or "",
            "embedding_api_key": embedding_provider.api_key,
            "embedding_dimensions": 1024,
        })


async def _resolve_embedding(
    db: AsyncSession | None,
    project: TextProject | None,
    embedding_model_override: str | None = None,
) -> tuple[AIProviderConfig | None, str]:
    from app.services.ai import resolve_explicit_component_model, get_available_embedding_models

    selected_model = str(embedding_model_override or "").strip()
    if not selected_model:
        selected_model = resolve_explicit_component_model(project, "memory_embedding")
    if not selected_model and db is not None:
        emb_models = await get_available_embedding_models(db)
        if emb_models:
            first = emb_models[0]
            selected_model = str(first if isinstance(first, str) else first.get("id", "")).strip()
    if not selected_model:
        raise RuntimeError("Cognee requires an embedding model.")
    provider, model = await _resolve_provider_for_model(db, model=selected_model, kind="embedding")
    if provider is None:
        raise RuntimeError(f'Cognee embedding model "{selected_model}" has no active provider.')
    return provider, model


def _split_memory_text(text: str, max_chars: int = 8000) -> list[str]:
    source = str(text or "").replace("\r\n", "\n").strip()
    if not source:
        return []
    if len(source) <= max_chars:
        return [source]
    paragraphs = [item.strip() for item in re.split(r"\n{2,}", source) if item.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append("\n\n".join(current).strip())
                current = []
                current_len = 0
            cursor = 0
            while cursor < len(paragraph):
                chunks.append(paragraph[cursor: cursor + max_chars].strip())
                cursor += max_chars
            continue
        next_len = current_len + len(paragraph) + (2 if current else 0)
        if current and next_len > max_chars:
            chunks.append("\n\n".join(current).strip())
            current = [paragraph]
            current_len = len(paragraph)
            continue
        current.append(paragraph)
        current_len = next_len
    if current:
        chunks.append("\n\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _ontology_text(ontology: dict[str, Any] | None) -> str:
    if not isinstance(ontology, dict) or not ontology:
        return ""
    return "[Project Ontology]\n" + json.dumps(ontology, ensure_ascii=False, indent=2)


async def _cognee_add(
    text: str,
    project_id: str,
    *,
    llm_provider: AIProviderConfig | None,
    llm_model: str,
    embedding_provider: AIProviderConfig | None,
    embedding_model: str,
) -> None:
    import cognee

    await _ensure_cognee_initialized()
    await _configure_cognee(
        llm_provider=llm_provider,
        llm_model=llm_model,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )
    dataset_name = f"project_{project_id}"
    await cognee.add(data=text, dataset_name=dataset_name)
    try:
        await asyncio.wait_for(
            cognee.cognify(datasets=[dataset_name]),
            timeout=_COGNEE_INGEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("Cognee cognify timed out after %ss (project=%s)", int(_COGNEE_INGEST_TIMEOUT), project_id)
        raise


async def _record_cognee_usage(
    *,
    project_id: str,
    db: AsyncSession | None,
    project: TextProject | None,
    llm_model: str | None,
    embedding_model: str | None,
    operation_id: str | None,
) -> None:
    if db is None:
        return
    project = project or await _load_project(project_id, db)
    user_id = str(getattr(project, "user_id", "") or "").strip()
    if not user_id:
        return

    from app.services.ai import record_model_usage

    if operation_id:
        operation = await db.get(TextOperation, operation_id)
    else:
        operation = None

    if llm_model:
        cost = await record_model_usage(
            model=llm_model,
            input_tokens=0,
            output_tokens=0,
            db=db,
            billing_user_id=user_id,
            billing_project_id=project_id,
            billing_operation_id=operation_id,
            source="memory_llm",
        )
        if operation is not None and cost:
            operation.cost = (operation.cost or 0) + cost

    if embedding_model:
        cost = await record_model_usage(
            model=embedding_model,
            input_tokens=0,
            output_tokens=0,
            db=db,
            billing_user_id=user_id,
            billing_project_id=project_id,
            billing_operation_id=operation_id,
            source="memory_embedding",
        )
        if operation is not None and cost:
            operation.cost = (operation.cost or 0) + cost


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def close_memory_runtime() -> None:
    return None


async def build_project_memory(
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
    memory_id = str(memory_id_override or "").strip() or str(project_id)
    source = str(text or "").strip()
    if not source:
        raise ValueError("Cognee build requires non-empty project text.")

    embedding_provider, resolved_embedding_model = await _resolve_embedding(db, None, embedding_model)
    llm_provider: AIProviderConfig | None = None
    resolved_llm_model = ""
    if model:
        llm_provider, resolved_llm_model = await _resolve_provider_for_model(db, model=model, kind="chat")

    if reset:
        if progress_callback:
            progress_callback(20, "Resetting Cognee project memory...", "setup", {"memory_id": memory_id})
        await delete_project_memory(project_id, db=db, embedding_model=resolved_embedding_model)

    ontology_payload = _ontology_text(ontology)
    if ontology_payload:
        await _cognee_add(
            ontology_payload,
            project_id,
            llm_provider=llm_provider,
            llm_model=resolved_llm_model,
            embedding_provider=embedding_provider,
            embedding_model=resolved_embedding_model,
        )

    chunks = _split_memory_text(source)
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        if progress_callback:
            progress = 25 + int((index - 1) / max(1, total) * 70)
            progress_callback(progress, f"Cognee ingesting chunk {index}/{total}...", "ingesting", {
                "processed": index - 1,
                "total": total,
                "memory_id": memory_id,
            })
        await _cognee_add(
            chunk,
            project_id,
            llm_provider=llm_provider,
            llm_model=resolved_llm_model,
            embedding_provider=embedding_provider,
            embedding_model=resolved_embedding_model,
        )

    if progress_callback:
        progress_callback(100, "Cognee project memory is ready.", "completed", {
            "processed": total,
            "total": total,
            "memory_id": memory_id,
        })

    if db is not None:
        project = await _load_project(project_id, db)
        if project is not None and not _project_memory_id(project):
            project.memory_id = memory_id
            await db.flush()

    await _record_cognee_usage(
        project_id=project_id,
        db=db,
        project=None,
        llm_model=resolved_llm_model or None,
        embedding_model=resolved_embedding_model,
        operation_id=operation_id,
    )
    return memory_id


async def search_project_memory(
    project_id: str,
    query: str,
    *,
    top_k: int = 10,
    db: AsyncSession | None = None,
    project: TextProject | None = None,
    operation_id: str | None = None,
) -> list[dict[str, Any]]:
    _, resolved_embedding_model = await _resolve_embedding(db, project)
    await _ensure_cognee_initialized()

    import cognee

    provider, model = await _resolve_provider_for_model(db, model=resolved_embedding_model, kind="embedding")
    if provider is not None:
        cognee.config.set_embedding_config({
            "embedding_provider": "huggingface",
            "embedding_model": f"openai/{model}" if not model.startswith("openai/") else model,
            "embedding_endpoint": provider.base_url or "",
            "embedding_api_key": provider.api_key,
            "embedding_dimensions": 1024,
        })

    dataset_name = f"project_{project_id}"
    try:
        results = await asyncio.wait_for(
            cognee.search(
                query_text=str(query or "").strip(),
                query_type=cognee.SearchType.CHUNKS,
                datasets=[dataset_name],
                top_k=max(1, int(top_k or 10)),
            ),
            timeout=_COGNEE_INGEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("Cognee search timed out after %ss (project=%s)", int(_COGNEE_INGEST_TIMEOUT), project_id)
        return []
    except Exception as exc:
        logger.warning("Cognee search failed for project %s: %s", project_id, exc)
        return []

    rows: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    for search_result in (results or []):
        items = getattr(search_result, "search_result", None)
        if items is None:
            items = search_result if isinstance(search_result, list) else []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                text_val = str(item.get("text") or item.get("content") or "").strip()
                if not text_val or text_val in seen_content:
                    continue
                seen_content.add(text_val)
                rows.append({
                    "id": str(item.get("id") or ""),
                    "content": text_val,
                    "type": str(item.get("type") or "chunk"),
                    "score": float(item.get("score") or 0),
                    "channel": "cognee",
                    "metadata": {
                        "tags": [],
                        "retrieval_source": "cognee_chunks",
                    },
                })
            elif isinstance(item, str):
                text_val = item.strip()
                if not text_val or text_val in seen_content:
                    continue
                seen_content.add(text_val)
                rows.append({
                    "id": "",
                    "content": text_val,
                    "type": "chunk",
                    "score": 0.0,
                    "channel": "cognee",
                    "metadata": {"retrieval_source": "cognee_chunks"},
                })

    await _record_cognee_usage(
        project_id=project_id,
        db=db,
        project=project,
        llm_model=None,
        embedding_model=resolved_embedding_model,
        operation_id=operation_id,
    )
    return rows


async def delete_project_memory(
    project_id: str,
    *,
    db: AsyncSession | None = None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    await _ensure_cognee_initialized()
    import cognee

    dataset_name = f"project_{project_id}"
    try:
        await cognee.forget(dataset=dataset_name, everything=True)
        return {"status": "forgotten", "dataset": dataset_name}
    except Exception as exc:
        logger.warning("Cognee forget() failed for project %s; falling back to prune: %s", project_id, exc)
        try:
            await cognee.prune.prune_data()
            await cognee.prune.prune_system()
            return {"status": "pruned", "project_id": project_id}
        except Exception as prune_exc:
            logger.exception("Cognee prune also failed for project %s: %s", project_id, prune_exc)
            return {"status": "error", "error": str(prune_exc)}


async def has_project_memory(
    project_id: str,
    *,
    db: AsyncSession | None = None,
    project: TextProject | None = None,
) -> bool:
    if project is None:
        project = await _load_project(project_id, db)
    memory_id = _project_memory_id(project)
    if not memory_id:
        return False

    await _ensure_cognee_initialized()
    import cognee

    try:
        snapshot = await cognee.export(
            dataset=str(project_id),
            format="pydantic",
            link_relations=False,
        )
    except Exception:
        return False
    if snapshot is None:
        return False
    nodes = getattr(snapshot, "nodes", None) or []
    edges = getattr(snapshot, "edges", None) or []
    return len(nodes) > 0 or len(edges) > 0


async def export_project_memory(
    project_id: str,
    *,
    db: AsyncSession | None = None,
    project: TextProject | None = None,
    memory_id_override: str | None = None,
) -> dict[str, Any]:
    await _ensure_cognee_initialized()
    import cognee

    try:
        snapshot = await cognee.export(
            dataset=str(project_id),
            format="pydantic",
            link_relations=True,
        )
    except Exception as exc:
        logger.warning("Cognee export failed for project %s: %s", project_id, exc)
        return {"nodes": [], "edges": [], "memories": []}

    if snapshot is None:
        return {"nodes": [], "edges": [], "memories": []}

    nodes: list[dict[str, Any]] = []
    for node in (getattr(snapshot, "nodes", None) or []):
        content = getattr(node, "text", None) or getattr(node, "name", None) or ""
        label = getattr(node, "name", None) or getattr(node, "text", None) or str(getattr(node, "id", ""))
        node_type = getattr(node, "type", None)
        if node_type is not None and not isinstance(node_type, str):
            node_type = getattr(node_type, "__name__", None) or str(node_type)

        properties: dict[str, Any] = {}
        if hasattr(node, "model_dump"):
            try:
                dumped = node.model_dump()
                if isinstance(dumped, dict):
                    for key, value in dumped.items():
                        if key in ("id", "created_at", "updated_at", "metadata"):
                            continue
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            properties[key] = value
                        else:
                            properties[key] = str(value)
            except Exception:
                properties = {}

        nodes.append({
            "id": str(getattr(node, "id", "")),
            "label": (label[:240] if isinstance(label, str) else str(label)),
            "type": node_type or "DataPoint",
            "content": (content[:2000] if isinstance(content, str) else str(content)),
            "properties": properties,
        })

    edges: list[dict[str, Any]] = []
    for edge in (getattr(snapshot, "edges", None) or []):
        source_id = str(getattr(edge, "source_id", ""))
        target_id = str(getattr(edge, "target_id", ""))
        relationship = str(getattr(edge, "relationship", "RELATED_TO"))
        edges.append({
            "id": f"{source_id}->{target_id}:{relationship}",
            "source": source_id,
            "target": target_id,
            "type": relationship,
            "label": relationship,
            "weight": 1.0,
            "properties": dict(getattr(edge, "properties", None) or {}),
        })

    return {"nodes": nodes, "edges": edges, "memories": []}


async def writeback_agent_memory(
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
    from app.services.ai import resolve_explicit_component_model

    project = project or await _load_project(project_id, db)
    if project is None:
        raise RuntimeError("Project is required for agent memory writeback.")

    memory_id = _project_memory_id(project) or str(project_id)
    embedding_provider, resolved_embedding_model = await _resolve_embedding(
        db, project, embedding_model_override
    )
    llm_model = llm_model_override or resolve_explicit_component_model(project, "memory_build") or ""
    llm_provider: AIProviderConfig | None = None
    resolved_llm_model = ""
    if llm_model:
        llm_provider, resolved_llm_model = await _resolve_provider_for_model(db, model=llm_model, kind="chat")

    state = dict(getattr(project, "creative_state", None) or {})
    ws = dict(state.get("agent_workspace") or {})
    ws.update(payload)
    state["agent_workspace"] = ws
    project.creative_state = state
    if db is not None:
        await db.flush()

    if not _project_memory_id(project):
        project.memory_id = memory_id
        if db is not None:
            await db.flush()

    # 整个 structured_memory 全量序列化后一次性写入 cognee。
    # 不再按 key 分类前缀——cognee 的 cognify() 会自动提取语义结构。
    sm = payload.get("structured_memory")
    sm_text = ""
    if isinstance(sm, (dict, list)):
        sm_text = json.dumps(sm, ensure_ascii=False, indent=2)
    elif isinstance(sm, str):
        sm_text = sm

    count = 0
    if sm_text.strip():
        await _cognee_add(
            sm_text,
            project_id,
            llm_provider=llm_provider,
            llm_model=resolved_llm_model,
            embedding_provider=embedding_provider,
            embedding_model=resolved_embedding_model,
        )
        count += 1

    source = str(source_text or "").strip()
    if source:
        for chunk in _split_memory_text(source):
            await _cognee_add(
                chunk,
                project_id,
                llm_provider=llm_provider,
                llm_model=resolved_llm_model,
                embedding_provider=embedding_provider,
                embedding_model=resolved_embedding_model,
            )
            count += 1

    await _record_cognee_usage(
        project_id=project_id,
        db=db,
        project=project,
        llm_model=resolved_llm_model or None,
        embedding_model=resolved_embedding_model,
        operation_id=operation_id,
    )

    return {"status": "ok", "count": count, "memory_id": memory_id}


async def retrieve_creative_memory(
    *,
    project_id: str,
    project: TextProject,
    query_plan: list[dict[str, Any]],
    context_query: str,
    db: AsyncSession,
) -> dict[str, Any]:
    lanes: dict[str, list[dict[str, Any]]] = {}
    plan_results: list[list[dict[str, Any]]] = []

    for item in query_plan:
        query_text = str(item.get("query") or "").strip()
        top_k = int(item.get("top_k") or 8)
        lane = str(item.get("lane") or "").strip()
        rows = await search_project_memory(
            project_id,
            query_text,
            top_k=top_k,
            db=db,
            project=project,
        )
        plan_results.append(rows)
        if lane:
            lanes[lane] = rows

    context_rows = await search_project_memory(
        project_id,
        context_query,
        top_k=8,
        db=db,
        project=project,
    )

    memory: dict[str, Any] = {
        "enabled": True,
        "retrieval_context": "",
        "entities": [],
        "relationships": lanes.get("relationships", []),
        "submemory": {"nodes": [], "edges": []},
        "plan_results": plan_results,
    }
    for key in ("typed_insights", "relationships", "continuity_state", "source_evidence", "summaries", "generation_hints", "style_voice"):
        memory[key] = lanes.get(key, [])

    context_lines: list[str] = []
    for row in context_rows:
        row_type = str(row.get("type") or "").strip()
        score = row.get("score")
        prefix = f"[{row_type} score={score}]" if score is not None else f"[{row_type}]"
        context_lines.append(f"{prefix} {row.get('content')}")
    memory["retrieval_context"] = "\n".join(context_lines)

    return memory

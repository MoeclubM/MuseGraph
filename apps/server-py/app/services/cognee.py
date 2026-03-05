import asyncio
from enum import Enum
import json
import logging
import os
import re
from typing import Any, Callable

import asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import AIProviderConfig
from app.services.ai import DEFAULT_MODEL, _load_llm_runtime_config, call_llm, detect_provider
from app.services.llm_json import extract_json_object
from app.services.provider_models import get_provider_chat_models, get_provider_embedding_models

logger = logging.getLogger(__name__)

# Lazy-loaded SearchType mapping — built once on first use.
_SEARCH_TYPE_MAP: dict[str, Any] | None = None
_DEFAULT_SEARCH_TYPE: Any | None = None
_MAX_VISUALIZATION_NODES = 320
_MAX_VISUALIZATION_EDGES = 900
_MAX_FRONTIER_PER_HOP = 360
_MAX_SEED_IDS = 120
_MAX_ALIAS_LLM_CANDIDATE_PAIRS = 36
_MAX_ALIAS_DECISION_CACHE = 128
_TIKTOKEN_PATCHED = False
_LITELLM_AEMBEDDING_PATCHED = False
_LITELLM_ACOMPLETION_PATCHED = False

_NODE_TYPE_ALIASES: dict[str, str] = {
    "textsummary": "TextSummary",
    "summary": "TextSummary",
    "entitytype": "EntityType",
    "entity_type": "EntityType",
    "documentchunk": "DocumentChunk",
    "chunk": "DocumentChunk",
    "textdocument": "TextDocument",
    "document": "TextDocument",
    "entity": "Entity",
}

_NODE_TYPE_PRIORITY: dict[str, int] = {
    "Entity": 120,
    "EntityType": 110,
    "TextSummary": 100,
    "TextDocument": 70,
    "DocumentChunk": 55,
}

_STRUCTURAL_NODE_TYPES: set[str] = {
    "TextDocument",
    "DocumentChunk",
    "TextSummary",
    "EntityType",
    "NodeSet",
    "RuleSet",
    "Rule",
}
_STRUCTURAL_NODE_NAMES: set[str] = {
    "coding_agent_rules",
}
_ALIAS_DECISION_CACHE: dict[str, dict[tuple[str, str], bool]] = {}


def _runtime_litellm_timeout_seconds() -> int:
    try:
        return max(5, min(1800, int(os.getenv("MUSEGRAPH_LLM_REQUEST_TIMEOUT_SECONDS", "180"))))
    except Exception:
        return 180


def _runtime_litellm_retry_count() -> int:
    try:
        return max(0, min(10, int(os.getenv("MUSEGRAPH_LLM_RETRY_COUNT", "4"))))
    except Exception:
        return 4


def _runtime_litellm_retry_interval_seconds() -> float:
    try:
        return max(0.0, min(60.0, float(os.getenv("MUSEGRAPH_LLM_RETRY_INTERVAL_SECONDS", "2"))))
    except Exception:
        return 2.0


def _is_retryable_litellm_error(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
        if 500 <= status_code <= 599:
            return True

    text = str(exc or "").lower()
    retryable_markers = ("timeout", "timed out", "gateway", "temporary", "rate limit", "connection")
    return any(marker in text for marker in retryable_markers)


async def _run_litellm_with_retry(request_factory: Callable[[], Any]) -> Any:
    attempts = max(1, _runtime_litellm_retry_count() + 1)
    retry_interval_seconds = _runtime_litellm_retry_interval_seconds()
    timeout_seconds = _runtime_litellm_timeout_seconds()
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await asyncio.wait_for(request_factory(), timeout=timeout_seconds)
        except Exception as exc:
            last_exc = exc
            should_retry = attempt < (attempts - 1) and _is_retryable_litellm_error(exc)
            if not should_retry:
                raise
            await asyncio.sleep(retry_interval_seconds)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("litellm request failed without exception")


def _normalize_entity_alias_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = re.sub(r"[\s·•・'\"`’‘“”\-\._:：,，;；/\\\(\)\[\]\{\}<>《》【】!！?？]+", "", text)
    return normalized.lower()


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _resolve_cognee_database_url() -> str:
    override = (settings.COGNEE_DATABASE_URL or "").strip()
    if override:
        return override
    return (settings.DATABASE_URL or "").strip()


def _parse_postgres_url(url: str):
    try:
        parsed = make_url(url)
    except Exception:
        return None
    driver = str(parsed.drivername or "").lower()
    if not driver.startswith("postgresql"):
        return None
    return parsed


def _resolve_cognee_relational_postgres_config() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    db_url = _resolve_cognee_database_url()
    if not db_url:
        return None, None
    parsed = _parse_postgres_url(db_url)
    if not parsed:
        return None, None

    db_name = str(parsed.database or "").strip()
    db_host = str(parsed.host or "").strip()
    db_port = str(parsed.port or "5432").strip()
    db_username = str(parsed.username or "").strip()
    db_password = str(parsed.password or "").strip()
    if not (db_name and db_host and db_username):
        return None, None

    relational_config = {
        "db_provider": "postgres",
        "db_name": db_name,
        "db_host": db_host,
        "db_port": db_port,
        "db_username": db_username,
        "db_password": db_password,
    }
    migration_config = {
        "migration_db_provider": "postgres",
        "migration_db_name": db_name,
        "migration_db_host": db_host,
        "migration_db_port": db_port,
        "migration_db_username": db_username,
        "migration_db_password": db_password,
    }
    return relational_config, migration_config


async def _ensure_cognee_postgres_database_exists() -> None:
    target = _parse_postgres_url(_resolve_cognee_database_url())
    if not target:
        return

    target_db_name = str(target.database or "").strip()
    db_host = str(target.host or "").strip()
    db_port = int(target.port or 5432)
    db_username = str(target.username or "").strip()
    db_password = str(target.password or "").strip()
    if not (target_db_name and db_host and db_username):
        return

    # Guard against identifier injection when composing CREATE DATABASE.
    if not re.fullmatch(r"[A-Za-z0-9_]+", target_db_name):
        return

    admin_source = _parse_postgres_url((settings.DATABASE_URL or "").strip()) or target
    admin_db_name = str(admin_source.database or "").strip() or "postgres"

    conn = await asyncpg.connect(
        host=db_host,
        port=db_port,
        user=db_username,
        password=db_password,
        database=admin_db_name,
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1 LIMIT 1",
            target_db_name,
        )
        if exists:
            return
        await conn.execute(f'CREATE DATABASE "{target_db_name}"')
    finally:
        await conn.close()


def _seed_cognee_relational_env() -> None:
    relational_config, migration_config = _resolve_cognee_relational_postgres_config()
    if relational_config:
        env_mapping = {
            "DB_PROVIDER": "db_provider",
            "DB_NAME": "db_name",
            "DB_HOST": "db_host",
            "DB_PORT": "db_port",
            "DB_USERNAME": "db_username",
            "DB_PASSWORD": "db_password",
        }
        for env_key, config_key in env_mapping.items():
            value = str(relational_config.get(config_key) or "").strip()
            if value:
                os.environ[env_key] = value
    if migration_config:
        migration_env_mapping = {
            "MIGRATION_DB_PROVIDER": "migration_db_provider",
            "MIGRATION_DB_NAME": "migration_db_name",
            "MIGRATION_DB_HOST": "migration_db_host",
            "MIGRATION_DB_PORT": "migration_db_port",
            "MIGRATION_DB_USERNAME": "migration_db_username",
            "MIGRATION_DB_PASSWORD": "migration_db_password",
        }
        for env_key, config_key in migration_env_mapping.items():
            value = str(migration_config.get(config_key) or "").strip()
            if value:
                os.environ[env_key] = value


def _alias_pair_key(left: str, right: str) -> tuple[str, str]:
    left_key = _normalize_entity_alias_key(left)
    right_key = _normalize_entity_alias_key(right)
    if left_key <= right_key:
        return left_key, right_key
    return right_key, left_key


def _is_llm_alias_candidate(left: str, right: str) -> bool:
    left_key = _normalize_entity_alias_key(left)
    right_key = _normalize_entity_alias_key(right)
    if not left_key or not right_key or left_key == right_key:
        return False
    if not (_contains_cjk(left_key) and _contains_cjk(right_key)):
        return False
    shorter, longer = (left_key, right_key) if len(left_key) <= len(right_key) else (right_key, left_key)
    if len(shorter) < 2:
        return False
    if len(longer) - len(shorter) > 4:
        return False
    return shorter in longer


def _collect_llm_alias_pairs(nodes: list[dict[str, Any]], *, limit: int = _MAX_ALIAS_LLM_CANDIDATE_PAIRS) -> list[dict[str, str]]:
    names: list[str] = []
    for node in nodes:
        node_type = str(node.get("type") or "")
        if node_type in _STRUCTURAL_NODE_TYPES:
            continue
        name = str(node.get("name") or node.get("label") or "").strip()
        if not name:
            continue
        names.append(name)

    if len(names) < 2:
        return []

    scored_pairs: list[tuple[int, str, str, tuple[str, str]]] = []
    seen_pair_keys: set[tuple[str, str]] = set()
    for idx, left in enumerate(names):
        for right in names[idx + 1 :]:
            if not _is_llm_alias_candidate(left, right):
                continue
            pair_key = _alias_pair_key(left, right)
            if not pair_key[0] or not pair_key[1] or pair_key in seen_pair_keys:
                continue
            seen_pair_keys.add(pair_key)
            shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
            score = 0
            if str(longer).endswith(str(shorter)):
                score += 3
            if str(longer).startswith(str(shorter)):
                score += 2
            score += max(0, 4 - abs(len(_normalize_entity_alias_key(left)) - len(_normalize_entity_alias_key(right))))
            scored_pairs.append((score, left, right, pair_key))

    if not scored_pairs:
        return []

    scored_pairs.sort(key=lambda item: (item[0], -len(item[1]), -len(item[2])), reverse=True)
    pairs: list[dict[str, str]] = []
    for _, left, right, pair_key in scored_pairs[: max(1, int(limit))]:
        pairs.append(
            {
                "left": left,
                "right": right,
                "left_key": pair_key[0],
                "right_key": pair_key[1],
            }
        )
    return pairs


def _to_bool_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"true", "1", "yes", "y", "same", "alias", "same_entity"}:
        return True
    if text in {"false", "0", "no", "n", "different", "not_alias", "not_same"}:
        return False
    return None


async def _resolve_alias_merge_decisions_with_llm(
    nodes: list[dict[str, Any]],
    *,
    db: AsyncSession,
    model: str | None = None,
    max_pairs: int = _MAX_ALIAS_LLM_CANDIDATE_PAIRS,
) -> dict[tuple[str, str], bool]:
    pairs = _collect_llm_alias_pairs(nodes, limit=max_pairs)
    if not pairs:
        return {}

    signature = json.dumps(
        [{"left_key": item["left_key"], "right_key": item["right_key"]} for item in pairs],
        ensure_ascii=False,
        sort_keys=True,
    )
    cached = _ALIAS_DECISION_CACHE.get(signature)
    if cached is not None:
        return dict(cached)

    selected_model = (model or "").strip() or DEFAULT_MODEL
    prompt = (
        "你是知识图谱实体对齐器。请判断每对名称是否指向同一个实体。\n"
        "严格规则：\n"
        "1) 人物名 vs 事件短语（如“贾母”与“贾母去世/贾母丧事”）= false。\n"
        "2) 人物名 vs 场景地点短语（如“贾母屋/贾母正室”）= false。\n"
        "3) 人物全名与简称/别称（如“林黛玉”与“黛玉”）= true。\n"
        "4) 不确定时返回 false。\n"
        "只输出 JSON，不要解释。格式：\n"
        '{"decisions":[{"left":"...","right":"...","same_entity":true,"confidence":0.0}]}\n\n'
        f"Pairs:\n{json.dumps([{'left': item['left'], 'right': item['right']} for item in pairs], ensure_ascii=False)}"
    )

    llm_result = await call_llm(selected_model, prompt, db, max_tokens=900)
    payload = extract_json_object(str(llm_result.get("content") or "")) or {}
    decisions_raw = payload.get("decisions") if isinstance(payload, dict) else None
    decision_map: dict[tuple[str, str], bool] = {}
    if isinstance(decisions_raw, list):
        for item in decisions_raw:
            if not isinstance(item, dict):
                continue
            left = str(item.get("left") or item.get("a") or item.get("name_a") or "").strip()
            right = str(item.get("right") or item.get("b") or item.get("name_b") or "").strip()
            if not left or not right:
                continue
            flag = _to_bool_flag(item.get("same_entity"))
            if flag is None:
                flag = _to_bool_flag(item.get("same"))
            if flag is None:
                continue
            pair_key = _alias_pair_key(left, right)
            if pair_key[0] and pair_key[1]:
                decision_map[pair_key] = flag

    _ALIAS_DECISION_CACHE[signature] = dict(decision_map)
    while len(_ALIAS_DECISION_CACHE) > _MAX_ALIAS_DECISION_CACHE:
        oldest = next(iter(_ALIAS_DECISION_CACHE))
        _ALIAS_DECISION_CACHE.pop(oldest, None)
    return decision_map


def _is_alias_name(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if not (_contains_cjk(left) and _contains_cjk(right)):
        return False

    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) < 2:
        return False
    if len(longer) - len(shorter) > 2:
        return False
    return longer.endswith(shorter)


def _should_merge_alias(
    left_key: str,
    right_key: str,
    alias_decisions: dict[tuple[str, str], bool] | None = None,
) -> bool:
    pair_key = _alias_pair_key(left_key, right_key)
    if alias_decisions is not None and pair_key in alias_decisions:
        return bool(alias_decisions[pair_key])
    return _is_alias_name(left_key, right_key)


def _merge_alias_entities(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    alias_decisions: dict[tuple[str, str], bool] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not nodes:
        return nodes, edges

    candidates: list[tuple[str, str]] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        node_type = str(node.get("type") or "")
        if node_type in _STRUCTURAL_NODE_TYPES:
            continue
        name = str(node.get("name") or node.get("label") or "").strip()
        key = _normalize_entity_alias_key(name)
        if not key:
            continue
        candidates.append((node_id, key))

    if len(candidates) < 2:
        return nodes, edges

    parent: dict[str, str] = {node_id: node_id for node_id, _ in candidates}
    key_map: dict[str, str] = {}

    def _find(node_id: str) -> str:
        current = parent.get(node_id, node_id)
        if current != node_id:
            current = _find(current)
            parent[node_id] = current
        return current

    def _union(left_id: str, right_id: str) -> None:
        left_root = _find(left_id)
        right_root = _find(right_id)
        if left_root == right_root:
            return
        left_key = key_map.get(left_root, "")
        right_key = key_map.get(right_root, "")
        if len(right_key) > len(left_key):
            left_root, right_root = right_root, left_root
            left_key, right_key = right_key, left_key
        parent[right_root] = left_root
        key_map[left_root] = left_key or right_key

    for node_id, key in candidates:
        key_map.setdefault(node_id, key)
        for existing_id, existing_key in list(key_map.items()):
            if existing_id == node_id:
                continue
            if _should_merge_alias(key, existing_key, alias_decisions):
                _union(node_id, existing_id)
                break

    remap: dict[str, str] = {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        root = _find(node_id) if node_id in parent else node_id
        remap[node_id] = root
        groups.setdefault(root, []).append(node)

    merged_nodes: list[dict[str, Any]] = []
    for root, grouped_nodes in groups.items():
        if len(grouped_nodes) == 1:
            merged_nodes.append(grouped_nodes[0])
            continue
        representative = max(
            grouped_nodes,
            key=lambda item: len(_normalize_entity_alias_key(item.get("name") or item.get("label"))),
        )
        aliases = sorted(
            {
                str(item.get("name") or item.get("label") or "").strip()
                for item in grouped_nodes
                if str(item.get("name") or item.get("label") or "").strip()
            }
        )
        base_name = str(representative.get("name") or representative.get("label") or "").strip()
        alias_list = [name for name in aliases if name and name != base_name]
        merged_node = dict(representative)
        merged_node["id"] = root
        merged_node["name"] = base_name or merged_node.get("name") or merged_node.get("label")
        if alias_list:
            merged_node["aliases"] = alias_list
        merged_nodes.append(merged_node)

    merged_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        source = remap.get(str(edge.get("source") or ""), str(edge.get("source") or ""))
        target = remap.get(str(edge.get("target") or ""), str(edge.get("target") or ""))
        label = str(edge.get("label") or "RELATED_TO")
        if not source or not target or source == target:
            continue
        edge_key = (source, target, label)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        merged_edge = dict(edge)
        merged_edge["source"] = source
        merged_edge["target"] = target
        merged_edges.append(merged_edge)

    return merged_nodes, merged_edges


def _dataset_name(project_id: str) -> str:
    return f"project-{project_id}"


def _build_search_type_map(search_type_enum: type[Enum]) -> tuple[dict[str, Any], Any | None]:
    supported_keys = {
        "INSIGHTS",
        "SUMMARIES",
        "CHUNKS",
        "GRAPH_COMPLETION",
        "RAG_COMPLETION",
        "GRAPH_SUMMARY_COMPLETION",
    }
    resolved: dict[str, Any] = {
        name: member
        for name, member in search_type_enum.__members__.items()
        if name.isupper() and name in supported_keys
    }
    if not resolved:
        return {}, None

    default_type = resolved.get("GRAPH_COMPLETION") or resolved.get("INSIGHTS") or next(iter(resolved.values()))

    return resolved, default_type


def _normalize_node_type(raw_type: Any) -> str:
    source = str(raw_type or "").strip()
    if not source:
        return "Entity"
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", source).strip("_")
    if not normalized:
        return "Entity"
    lower = normalized.lower()
    if lower in _NODE_TYPE_ALIASES:
        return _NODE_TYPE_ALIASES[lower]
    return source


def _node_category(node_type: str) -> str:
    if node_type == "TextDocument":
        return "document"
    if node_type == "DocumentChunk":
        return "chunk"
    if node_type == "TextSummary":
        return "summary"
    if node_type == "EntityType":
        return "schema"
    if node_type == "Entity":
        return "entity"
    return "other"


def _short_text(value: Any, *, limit: int = 90) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\[ONTOLOGY_CONTEXT\][\s\S]*?\[/ONTOLOGY_CONTEXT\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)] + "..."


def _build_node_label(*, node_id: str, node_type: str, props: dict[str, Any]) -> str:
    if node_type == "TextDocument":
        name = _short_text(props.get("name") or props.get("title") or props.get("text"), limit=72)
        return name or f"Document {node_id[:8]}"

    if node_type == "DocumentChunk":
        chunk_text = _short_text(props.get("text") or props.get("content"), limit=78)
        if chunk_text:
            return chunk_text
        return f"Chunk {node_id[:8]}"

    if node_type == "TextSummary":
        summary_text = _short_text(props.get("summary") or props.get("text") or props.get("content"), limit=78)
        if summary_text:
            return summary_text
        return f"Summary {node_id[:8]}"

    if node_type == "EntityType":
        name = _short_text(
            props.get("name")
            or props.get("entity_type")
            or props.get("type")
            or props.get("label"),
            limit=72,
        )
        return name or f"EntityType {node_id[:8]}"

    generic = _short_text(
        props.get("name")
        or props.get("label")
        or props.get("text")
        or props.get("summary")
        or node_id,
        limit=78,
    )
    return generic or node_id[:12]


def _node_priority(node: dict[str, Any], degree_map: dict[str, int]) -> int:
    node_type = str(node.get("type") or "").strip()
    priority = _NODE_TYPE_PRIORITY.get(node_type, 60)
    # Keep ontology semantic types (e.g. PERSON/PLACE) slightly above generic infra nodes.
    if node_type.isupper() and node_type not in _NODE_TYPE_PRIORITY:
        priority = max(priority, 95)
    return priority + min(20, degree_map.get(str(node.get("id") or ""), 0))


def _drop_structural_nodes_for_preview(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    semantic_nodes = [
        node
        for node in nodes
        if str(node.get("type") or "").strip() not in _STRUCTURAL_NODE_TYPES
        and str(node.get("name") or node.get("label") or "").strip().lower() not in _STRUCTURAL_NODE_NAMES
    ]
    if not semantic_nodes:
        # During early build stages Cognee may only expose structural nodes
        # (documents/chunks/summaries). Keep them so preview can update in real-time.
        fallback_nodes = [
            node
            for node in nodes
            if str(node.get("name") or node.get("label") or "").strip().lower() not in _STRUCTURAL_NODE_NAMES
        ]
        if not fallback_nodes:
            return [], []
        fallback_ids = {str(node.get("id") or "") for node in fallback_nodes}
        fallback_edges = [
            edge
            for edge in edges
            if str(edge.get("source") or "") in fallback_ids
            and str(edge.get("target") or "") in fallback_ids
        ]
        return fallback_nodes, fallback_edges

    semantic_ids = {str(node.get("id") or "") for node in semantic_nodes}
    semantic_edges = [
        edge
        for edge in edges
        if str(edge.get("source") or "") in semantic_ids
        and str(edge.get("target") or "") in semantic_ids
    ]
    if len(semantic_nodes) < 2:
        # Keep immediate structural neighbors for sparse graphs so the preview
        # can show connectivity instead of a single isolated entity node.
        neighbor_ids = set(semantic_ids)
        for edge in edges:
            src = str(edge.get("source") or "")
            tgt = str(edge.get("target") or "")
            if src in semantic_ids or tgt in semantic_ids:
                neighbor_ids.add(src)
                neighbor_ids.add(tgt)
        expanded_nodes = [
            node
            for node in nodes
            if str(node.get("id") or "") in neighbor_ids
            and str(node.get("name") or node.get("label") or "").strip().lower() not in _STRUCTURAL_NODE_NAMES
        ]
        expanded_edges = [
            edge
            for edge in edges
            if str(edge.get("source") or "") in neighbor_ids
            and str(edge.get("target") or "") in neighbor_ids
        ]
        if expanded_nodes:
            return expanded_nodes, expanded_edges
    # Keep semantic nodes even if relation extraction is still sparse.
    return semantic_nodes, semantic_edges


def _prune_graph_for_preview(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes, edges = _drop_structural_nodes_for_preview(nodes, edges)

    if len(nodes) <= _MAX_VISUALIZATION_NODES and len(edges) <= _MAX_VISUALIZATION_EDGES:
        return nodes, edges

    degree_map: dict[str, int] = {}
    for edge in edges:
        src = str(edge.get("source") or "")
        tgt = str(edge.get("target") or "")
        if src:
            degree_map[src] = degree_map.get(src, 0) + 1
        if tgt:
            degree_map[tgt] = degree_map.get(tgt, 0) + 1

    sorted_nodes = sorted(
        nodes,
        key=lambda node: (
            _node_priority(node, degree_map),
            degree_map.get(str(node.get("id") or ""), 0),
        ),
        reverse=True,
    )
    kept_nodes = sorted_nodes[:_MAX_VISUALIZATION_NODES]
    keep_ids = {str(node.get("id") or "") for node in kept_nodes}
    filtered_edges = [
        edge
        for edge in edges
        if str(edge.get("source") or "") in keep_ids and str(edge.get("target") or "") in keep_ids
    ]

    if len(filtered_edges) > _MAX_VISUALIZATION_EDGES:
        filtered_edges = sorted(
            filtered_edges,
            key=lambda edge: (
                degree_map.get(str(edge.get("source") or ""), 0)
                + degree_map.get(str(edge.get("target") or ""), 0)
            ),
            reverse=True,
        )[:_MAX_VISUALIZATION_EDGES]

    linked_ids: set[str] = set()
    for edge in filtered_edges:
        linked_ids.add(str(edge.get("source") or ""))
        linked_ids.add(str(edge.get("target") or ""))
    if linked_ids:
        kept_nodes = [node for node in kept_nodes if str(node.get("id") or "") in linked_ids]

    return kept_nodes, filtered_edges


def _pick_seed_ids(seed_ids: list[str], *, limit: int) -> list[str]:
    if limit <= 0:
        return []
    if len(seed_ids) <= limit:
        return list(seed_ids)

    # Evenly sample over the original dataset ordering so preview is not biased
    # toward only early chunks.
    picked: list[str] = []
    seen: set[str] = set()
    step = (len(seed_ids) - 1) / max(1, limit - 1)
    for index in range(limit):
        pos = int(round(index * step))
        pos = min(max(pos, 0), len(seed_ids) - 1)
        node_id = str(seed_ids[pos])
        if node_id and node_id not in seen:
            seen.add(node_id)
            picked.append(node_id)
    if len(picked) < limit:
        for node_id in seed_ids:
            if node_id in seen:
                continue
            seen.add(node_id)
            picked.append(str(node_id))
            if len(picked) >= limit:
                break
    return picked


def _get_search_type_map() -> dict[str, Any]:
    global _SEARCH_TYPE_MAP, _DEFAULT_SEARCH_TYPE
    if _SEARCH_TYPE_MAP is None:
        from cognee.api.v1.search import SearchType

        _SEARCH_TYPE_MAP, _DEFAULT_SEARCH_TYPE = _build_search_type_map(SearchType)
    return _SEARCH_TYPE_MAP


def _patch_cognee_runtime_compatibility() -> None:
    global _TIKTOKEN_PATCHED, _LITELLM_AEMBEDDING_PATCHED, _LITELLM_ACOMPLETION_PATCHED
    if not _TIKTOKEN_PATCHED:
        try:
            import tiktoken
            _orig_encoding_for_model = tiktoken.encoding_for_model

            def _patched_encoding_for_model(model_name: str):
                try:
                    return _orig_encoding_for_model(model_name)
                except KeyError:
                    return tiktoken.get_encoding("cl100k_base")

            tiktoken.encoding_for_model = _patched_encoding_for_model
            _TIKTOKEN_PATCHED = True
        except Exception:
            pass

    if not _LITELLM_AEMBEDDING_PATCHED:
        try:
            import litellm
            original = litellm.aembedding
            if getattr(original, "__musegraph_patched__", False):
                _LITELLM_AEMBEDDING_PATCHED = True
            else:
                async def _patched_aembedding(*args, **kwargs):
                    kwargs.pop("dimensions", None)
                    kwargs.setdefault("timeout", _runtime_litellm_timeout_seconds())
                    kwargs.setdefault("num_retries", 0)
                    return await _run_litellm_with_retry(lambda: original(*args, **kwargs))

                setattr(_patched_aembedding, "__musegraph_patched__", True)
                litellm.aembedding = _patched_aembedding
                _LITELLM_AEMBEDDING_PATCHED = True
        except Exception:
            pass

    if not _LITELLM_ACOMPLETION_PATCHED:
        try:
            import litellm
            original = litellm.acompletion
            if getattr(original, "__musegraph_patched__", False):
                _LITELLM_ACOMPLETION_PATCHED = True
            else:
                async def _patched_acompletion(*args, **kwargs):
                    kwargs.setdefault("timeout", _runtime_litellm_timeout_seconds())
                    kwargs.setdefault("num_retries", 0)
                    return await _run_litellm_with_retry(lambda: original(*args, **kwargs))

                setattr(_patched_acompletion, "__musegraph_patched__", True)
                litellm.acompletion = _patched_acompletion
                _LITELLM_ACOMPLETION_PATCHED = True
        except Exception:
            pass


async def setup_cognee():
    """Configure Cognee infrastructure. Runtime LLM/embedding settings are injected per request."""
    try:
        await _ensure_cognee_postgres_database_exists()
        _seed_cognee_relational_env()
        # Startup should not hard-fail on provider connectivity before WebUI runtime
        # configuration is loaded for each graph task.
        os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")
        _patch_cognee_runtime_compatibility()
        import cognee

        config_obj = getattr(cognee, "config", None)
        if config_obj:
            relational_config, migration_config = _resolve_cognee_relational_postgres_config()
            if relational_config and hasattr(config_obj, "set_relational_db_config"):
                config_obj.set_relational_db_config(relational_config)
            if migration_config and hasattr(config_obj, "set_migration_db_config"):
                config_obj.set_migration_db_config(migration_config)

        graph_payload = {
            "graph_database_provider": "neo4j",
            "graph_database_url": settings.NEO4J_URL,
            "graph_database_username": settings.NEO4J_USERNAME,
            "graph_database_password": settings.NEO4J_PASSWORD,
        }
        if config_obj and hasattr(config_obj, "set_graph_db_config"):
            config_obj.set_graph_db_config(graph_payload)

        # Ensure Cognee's internal relational database schema exists.
        try:
            from cognee.infrastructure.databases.relational import get_relational_engine
            engine = get_relational_engine()
            await engine.create_database()
        except Exception:
            pass
    except ImportError:
        pass  # Cognee not installed


def _with_model_prefix(model: str, provider: str) -> str:
    normalized = (model or "").strip()
    if not normalized:
        return normalized
    if "/" in normalized:
        return normalized
    prefix = "anthropic" if provider == "anthropic_compatible" else "openai"
    return f"{prefix}/{normalized}"


def _strip_model_provider_prefix(model: Any) -> str:
    text = str(model or "").strip()
    if not text:
        return ""
    if "/" in text:
        _, suffix = text.split("/", 1)
        return suffix.strip()
    return text


def _normalized_model_id(model: Any) -> str:
    return _strip_model_provider_prefix(model).lower()


def _model_id_matches(left: Any, right: Any) -> bool:
    left_id = _normalized_model_id(left)
    right_id = _normalized_model_id(right)
    if not left_id or not right_id:
        return False
    return left_id == right_id


def _first_valid_model(models: list[str]) -> str | None:
    for item in models:
        value = str(item or "").strip()
        if value:
            return value
    return None


def _select_provider_for_model(
    configs: list[AIProviderConfig],
    *,
    model: str,
    embedding: bool,
) -> tuple[AIProviderConfig | None, str | None]:
    getter = get_provider_embedding_models if embedding else get_provider_chat_models
    for provider in configs:
        provider_models = getter(provider)
        for candidate in provider_models:
            if _model_id_matches(candidate, model):
                return provider, str(candidate).strip() or str(model).strip()
    return None, None


def _require_provider_api_key(provider: AIProviderConfig, *, purpose: str) -> str:
    value = str(getattr(provider, "api_key", "") or "").strip()
    if value:
        return value
    provider_name = str(getattr(provider, "name", "") or getattr(provider, "id", "") or provider.provider)
    raise RuntimeError(
        f"Provider '{provider_name}' is missing API key for {purpose}. "
        "Please set provider key in WebUI."
    )


def _apply_cognee_embedding_config(
    *,
    config_obj: Any,
    model: str | None,
    api_key: str | None,
    endpoint: str | None,
    provider: str,
) -> None:
    selected_model = (model or "").strip()
    if not selected_model:
        return
    selected_api_key = (api_key or "").strip()
    selected_endpoint = (endpoint or "").strip()
    model_with_prefix = _with_model_prefix(selected_model, provider)

    payload: dict[str, Any] = {"embedding_model": model_with_prefix}
    if selected_api_key:
        payload["embedding_api_key"] = selected_api_key
    if selected_endpoint:
        payload["embedding_endpoint"] = selected_endpoint

    if config_obj:
        for method_name in ("set_embed_config", "set_embedding_config"):
            setter = getattr(config_obj, method_name, None)
            if callable(setter):
                try:
                    setter(payload)
                    break
                except Exception:
                    continue

    os.environ["EMBEDDING_MODEL"] = model_with_prefix
    os.environ["EMBEDDING_PROVIDER"] = provider
    if selected_api_key:
        os.environ["EMBEDDING_API_KEY"] = selected_api_key
    if selected_endpoint:
        os.environ["EMBEDDING_ENDPOINT"] = selected_endpoint


async def _configure_cognee_llm(
    *,
    model: str | None,
    embedding_model: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")
    _patch_cognee_runtime_compatibility()
    import cognee
    runtime_cfg = await _load_llm_runtime_config(db)
    os.environ["MUSEGRAPH_LLM_REQUEST_TIMEOUT_SECONDS"] = str(
        int(runtime_cfg.get("llm_request_timeout_seconds", 180))
    )
    os.environ["MUSEGRAPH_LLM_RETRY_COUNT"] = str(int(runtime_cfg.get("llm_retry_count", 4)))
    os.environ["MUSEGRAPH_LLM_RETRY_INTERVAL_SECONDS"] = str(
        float(runtime_cfg.get("llm_retry_interval_seconds", 2.0))
    )
    os.environ["MUSEGRAPH_LLM_PREFER_STREAM"] = "true" if bool(runtime_cfg.get("llm_prefer_stream", True)) else "false"
    os.environ["MUSEGRAPH_LLM_STREAM_FALLBACK_NONSTREAM"] = (
        "true" if bool(runtime_cfg.get("llm_stream_fallback_nonstream", True)) else "false"
    )

    selected_model = (model or "").strip()
    selected_embedding_model = (embedding_model or "").strip()
    if db is None:
        # Compatibility fallback for tests/standalone calls.
        provider = detect_provider(_strip_model_provider_prefix(selected_model)) if selected_model else "openai_compatible"
        api_key = (settings.COGNEE_LLM_API_KEY or settings.OPENAI_API_KEY).strip()
        base_url = (settings.COGNEE_LLM_BASE_URL or "").strip() or None
        if not selected_model:
            selected_model = (settings.COGNEE_LLM_MODEL or "").strip() or DEFAULT_MODEL
        if not api_key:
            logger.debug("Skip Cognee runtime provider injection because db is None and no fallback key is configured.")
            return
        llm_model_with_prefix = _with_model_prefix(selected_model, provider)
        llm_config: dict[str, Any] = {"llm_api_key": api_key, "llm_model": llm_model_with_prefix}
        if base_url:
            llm_config["llm_endpoint"] = base_url
        config_obj = getattr(cognee, "config", None)
        if config_obj and hasattr(config_obj, "set_llm_config"):
            config_obj.set_llm_config(llm_config)
        os.environ["LLM_MODEL"] = llm_model_with_prefix
        os.environ["LLM_API_KEY"] = api_key
        if base_url:
            os.environ["LLM_ENDPOINT"] = base_url
        _apply_cognee_embedding_config(
            config_obj=config_obj,
            model=selected_embedding_model or os.getenv("EMBEDDING_MODEL", "").strip() or None,
            api_key=(os.getenv("EMBEDDING_API_KEY", "").strip() or api_key),
            endpoint=(os.getenv("EMBEDDING_ENDPOINT", "").strip() or base_url),
            provider=os.getenv("EMBEDDING_PROVIDER", "").strip() or provider,
        )
        return

    result = await db.execute(
        select(AIProviderConfig)
        .where(AIProviderConfig.is_active == True)
        .order_by(AIProviderConfig.priority.desc())
    )
    configs = result.scalars().all()
    if not configs:
        raise RuntimeError("No active AI provider configured. Please configure provider and models in WebUI first.")

    llm_provider: AIProviderConfig | None = None
    resolved_model = selected_model
    if selected_model:
        llm_provider, matched_model = _select_provider_for_model(
            configs,
            model=selected_model,
            embedding=False,
        )
        if matched_model:
            resolved_model = matched_model

    if llm_provider is None and selected_model:
        expected_provider = detect_provider(_strip_model_provider_prefix(selected_model))
        for item in configs:
            if item.provider == expected_provider:
                llm_provider = item
                break

    if llm_provider is None:
        llm_provider = configs[0]

    if not resolved_model:
        resolved_model = _first_valid_model(get_provider_chat_models(llm_provider)) or ""

    if not resolved_model:
        for item in configs:
            first_chat = _first_valid_model(get_provider_chat_models(item))
            if first_chat:
                llm_provider = item
                resolved_model = first_chat
                break

    if not resolved_model:
        raise RuntimeError("No chat model configured in active providers. Please set chat models in WebUI.")

    llm_api_key = _require_provider_api_key(llm_provider, purpose="LLM")
    llm_provider_type = str(llm_provider.provider or "openai_compatible").strip() or "openai_compatible"
    llm_base_url = str(getattr(llm_provider, "base_url", "") or "").strip() or None

    embedding_provider_cfg: AIProviderConfig | None = None
    resolved_embedding_model = selected_embedding_model

    if selected_embedding_model:
        embedding_provider_cfg, matched_embedding = _select_provider_for_model(
            configs,
            model=selected_embedding_model,
            embedding=True,
        )
        if embedding_provider_cfg is None:
            raise RuntimeError(
                f"Embedding model '{selected_embedding_model}' is not configured in any active provider."
            )
        if matched_embedding:
            resolved_embedding_model = matched_embedding
    else:
        preferred_embedding = _first_valid_model(get_provider_embedding_models(llm_provider))
        if preferred_embedding:
            embedding_provider_cfg = llm_provider
            resolved_embedding_model = preferred_embedding
        else:
            for item in configs:
                fallback_embedding = _first_valid_model(get_provider_embedding_models(item))
                if fallback_embedding:
                    embedding_provider_cfg = item
                    resolved_embedding_model = fallback_embedding
                    break

    if embedding_provider_cfg is None or not resolved_embedding_model:
        raise RuntimeError("No embedding model configured in active providers. Please set embedding models in WebUI.")

    embedding_api_key = _require_provider_api_key(embedding_provider_cfg, purpose="embedding")
    embedding_provider_type = (
        str(embedding_provider_cfg.provider or "openai_compatible").strip() or "openai_compatible"
    )
    embedding_base_url = str(getattr(embedding_provider_cfg, "base_url", "") or "").strip() or None

    llm_config: dict[str, Any] = {
        "llm_api_key": llm_api_key,
        "llm_model": _with_model_prefix(resolved_model, llm_provider_type),
    }
    if llm_base_url:
        llm_config["llm_endpoint"] = llm_base_url
    config_obj = getattr(cognee, "config", None)
    if config_obj and hasattr(config_obj, "set_llm_config"):
        config_obj.set_llm_config(llm_config)

    os.environ["LLM_MODEL"] = str(llm_config["llm_model"])
    os.environ["LLM_API_KEY"] = llm_api_key
    os.environ["COGNEE_LLM_MODEL"] = str(llm_config["llm_model"])
    os.environ["COGNEE_LLM_API_KEY"] = llm_api_key
    if llm_base_url:
        os.environ["LLM_ENDPOINT"] = llm_base_url
        os.environ["COGNEE_LLM_BASE_URL"] = llm_base_url

    _apply_cognee_embedding_config(
        config_obj=config_obj,
        model=resolved_embedding_model,
        api_key=embedding_api_key,
        endpoint=embedding_base_url,
        provider=embedding_provider_type,
    )
    logger.info(
        "Configured Cognee runtime provider settings (llm_provider=%s, llm_model=%s, embedding_provider=%s, embedding_model=%s)",
        str(getattr(llm_provider, "name", "") or llm_provider.provider),
        _with_model_prefix(resolved_model, llm_provider_type),
        str(getattr(embedding_provider_cfg, "name", "") or embedding_provider_cfg.provider),
        _with_model_prefix(resolved_embedding_model, embedding_provider_type),
    )


async def add_and_cognify(
    project_id: str,
    text: str,
    *,
    model: str | None = None,
    embedding_model: str | None = None,
    db: AsyncSession | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> str:
    """Add text to a Cognee dataset, build knowledge graph, and enrich with memify."""
    import cognee

    def _emit_progress(progress: int, message: str) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(progress, message)
        except Exception:
            pass

    def _split_text_for_graph(payload: str, *, chunk_size: int = 12000, overlap: int = 600) -> list[str]:
        source = (payload or "").strip()
        if not source:
            return []
        if len(source) <= chunk_size:
            return [source]

        chunks: list[str] = []
        cursor = 0
        text_length = len(source)
        while cursor < text_length:
            end = min(cursor + chunk_size, text_length)
            if end < text_length:
                # Prefer paragraph boundary to keep chunk semantics.
                boundary = source.rfind("\n\n", cursor + max(1, int(chunk_size * 0.6)), end)
                if boundary > cursor:
                    end = boundary
            piece = source[cursor:end].strip()
            if piece:
                chunks.append(piece)
            if end >= text_length:
                break
            next_cursor = max(end - overlap, cursor + 1)
            if next_cursor <= cursor:
                next_cursor = end
            cursor = next_cursor
        return chunks or [source]

    await _configure_cognee_llm(model=model, embedding_model=embedding_model, db=db)

    dataset_name = _dataset_name(project_id)
    chunks = _split_text_for_graph(text)
    if not chunks:
        raise ValueError("No graph input text provided")

    total_chunks = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        await cognee.add(chunk, dataset_name=dataset_name)
        upload_progress = 5 + int((idx / total_chunks) * 55)
        _emit_progress(upload_progress, f"Uploading chunks {idx}/{total_chunks}...")

    _emit_progress(70, "Extracting entities and relations...")
    await cognee.cognify(datasets=[dataset_name])
    # Ensure enrichment is applied to the same dataset, not main_dataset.
    _emit_progress(88, "Applying memory enrichment...")
    memify_timeout_seconds = 180
    try:
        memify_task = asyncio.create_task(cognee.memify(dataset=dataset_name))
        done, pending = await asyncio.wait({memify_task}, timeout=memify_timeout_seconds)
        if pending:
            for task in pending:
                task.cancel()
            _emit_progress(95, "Memory enrichment timeout, finalizing graph...")
        else:
            memify_error = memify_task.exception()
            if memify_error is not None:
                _emit_progress(95, "Memory enrichment failed, finalizing graph...")
    except Exception:
        # Memify may hang on some provider/model combinations.
        # Keep graph build usable with cognify result instead of blocking forever.
        _emit_progress(95, "Memory enrichment skipped, finalizing graph...")
    _emit_progress(100, "Graph build complete")
    return dataset_name


def _parse_result(r: Any) -> dict[str, Any]:
    """Extract content from a single Cognee search result."""
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    def _extract_from_dict(data: dict[str, Any], *, default_type: str | None = None) -> dict[str, Any]:
        text = (
            data.get("text")
            or data.get("content")
            or data.get("summary")
            or data.get("answer")
            or data.get("result")
        )
        item: dict[str, Any] = {"content": _as_text(text)}
        node_type = data.get("type") or data.get("entity_type") or data.get("result_type") or default_type
        if node_type:
            item["type"] = str(node_type)
        score = data.get("score") or data.get("similarity") or data.get("distance")
        if isinstance(score, (int, float)):
            item["score"] = float(score)
        source_id = data.get("id") or data.get("uuid")
        if source_id:
            item["id"] = str(source_id)
        return item

    # Pydantic model / dataclass
    for attr in ("text", "content", "summary"):
        try:
            val = getattr(r, attr, None)
            if val and isinstance(val, str):
                base = {"content": val}
                result_type = getattr(r, "type", None) or r.__class__.__name__
                if result_type:
                    base["type"] = str(result_type)
                score = getattr(r, "score", None)
                if isinstance(score, (int, float)):
                    base["score"] = float(score)
                return base
        except Exception:
            pass
    # dict
    if isinstance(r, dict):
        parsed = _extract_from_dict(r)
        if parsed.get("content"):
            return parsed
    # model_dump fallback
    try:
        d = r.model_dump() if hasattr(r, "model_dump") else r.__dict__
        parsed = _extract_from_dict(d, default_type=r.__class__.__name__)
        if not parsed.get("content"):
            parsed["content"] = str(r)
        return parsed
    except Exception:
        return {"content": str(r)}


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
        "Given a user query and candidate passages, return strict JSON only.\n"
        "Schema:\n"
        '{"ranked":[{"id":1,"score":0.95}]}\n'
        "Rules:\n"
        "1) Keep only ids from provided candidates.\n"
        "2) score must be in [0, 1], sorted descending by relevance.\n"
        "3) Prefer factual grounding, temporal consistency, and direct answerability.\n"
        "4) Do not output markdown or explanations.\n\n"
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

    # Keep original retrieval coverage for ids omitted by reranker output.
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
    """Search the knowledge graph using Cognee's native search."""
    import cognee

    global _DEFAULT_SEARCH_TYPE
    normalized_search_type = str(search_type or "").strip().upper() or "INSIGHTS"
    type_map = _get_search_type_map()
    cognee_type = type_map.get(normalized_search_type) or _DEFAULT_SEARCH_TYPE
    if cognee_type is None:
        raise RuntimeError("No supported Cognee search types available in current environment.")

    try:
        results: Any = await cognee.search(
            query_text=query,
            query_type=cognee_type,
            top_k=top_k,
            datasets=[_dataset_name(project_id)],
        )
    except Exception as exc:
        raise RuntimeError(f"Cognee search failed for dataset {_dataset_name(project_id)}: {exc}") from exc

    if not isinstance(results, list):
        return [{"content": str(results), "score": 1.0}]

    parsed = []
    for r in results:
        item = _parse_result(r)
        item.setdefault("score", 1.0)
        parsed.append(item)

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
    """Get graph data for visualization via Cognee's graph engine."""
    from cognee.modules.data.methods import get_authorized_existing_datasets, get_dataset_data
    from cognee.modules.users.methods import get_default_user
    from cognee.infrastructure.databases.graph import get_graph_engine

    dataset_name = _dataset_name(project_id)
    try:
        user = await get_default_user()
        datasets = await get_authorized_existing_datasets([dataset_name], "read", user)
    except Exception as exc:
        raise RuntimeError(f"Failed to read graph dataset authorization for {dataset_name}: {exc}") from exc

    if not datasets:
        return {"nodes": [], "edges": []}

    dataset = datasets[0]
    try:
        dataset_data = await get_dataset_data(dataset.id)
    except Exception as exc:
        raise RuntimeError(f"Failed to load graph dataset {dataset_name}: {exc}") from exc

    seed_ids = [str(item.id) for item in dataset_data if getattr(item, "id", None)]
    if not seed_ids:
        return {"nodes": [], "edges": []}

    try:
        graph_engine = await get_graph_engine()
    except Exception as exc:
        raise RuntimeError(f"Failed to initialize graph engine for {dataset_name}: {exc}") from exc
    limited_seed_ids = _pick_seed_ids(seed_ids, limit=_MAX_SEED_IDS)
    frontier = set(limited_seed_ids)
    visited = set(limited_seed_ids)
    raw_nodes_acc: dict[str, dict[str, Any]] = {}
    raw_edges_acc: dict[tuple[str, str, str], dict[str, Any]] = {}

    # 3-hop neighborhood around dataset document nodes (document -> chunks -> entities).
    try:
        for _ in range(3):
            if not frontier:
                break
            frontier_batch = sorted(frontier)[:_MAX_FRONTIER_PER_HOP]
            raw_nodes, raw_edges = await graph_engine.get_id_filtered_graph_data(frontier_batch)
            next_frontier: set[str] = set()

            for n in raw_nodes:
                if not isinstance(n, tuple) or len(n) < 2:
                    continue
                node_id = str(n[0])
                props = n[1] if isinstance(n[1], dict) else {}
                raw_nodes_acc[node_id] = props
                if node_id not in visited:
                    next_frontier.add(node_id)

            for e in raw_edges:
                if not isinstance(e, tuple) or len(e) < 3:
                    continue
                src = str(e[0])
                tgt = str(e[1])
                label = str(e[2] or "")
                props = e[3] if len(e) > 3 and isinstance(e[3], dict) else {}
                raw_edges_acc[(src, tgt, label)] = props
                if src not in visited:
                    next_frontier.add(src)
                if tgt not in visited:
                    next_frontier.add(tgt)

            visited.update(next_frontier)
            frontier = next_frontier
    except Exception as exc:
        raise RuntimeError(f"Failed to read graph neighborhood for {dataset_name}: {exc}") from exc

    raw_nodes = [(node_id, props) for node_id, props in raw_nodes_acc.items()]
    raw_edges = [
        (src, tgt, label, props)
        for (src, tgt, label), props in raw_edges_acc.items()
    ]

    nodes: list[dict] = []
    edges: list[dict] = []

    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return {"nodes": nodes, "edges": edges}

    for n in raw_nodes:
        if isinstance(n, tuple) and len(n) >= 2:
            node_id = n[0]
            props = n[1] if isinstance(n[1], dict) else {}
        elif isinstance(n, dict):
            node_id = n.get("id", "")
            props = n
        else:
            continue
        normalized_type = _normalize_node_type(props.get("type"))
        nodes.append({
            "id": str(node_id),
            "label": _build_node_label(node_id=str(node_id), node_type=normalized_type, props=props),
            "type": normalized_type,
            "raw_type": str(props.get("type") or ""),
            "category": _node_category(normalized_type),
            "name": _short_text(props.get("name"), limit=96),
            "text_preview": _short_text(props.get("text") or props.get("content"), limit=220),
            "summary_preview": _short_text(props.get("summary"), limit=220),
        })

    for e in raw_edges:
        if isinstance(e, tuple) and len(e) >= 3:
            props = e[3] if len(e) > 3 and isinstance(e[3], dict) else {}
            edge_label = props.get("relationship_name", e[2])
            edges.append({
                "source": str(e[0]),
                "target": str(e[1]),
                "label": _short_text(edge_label, limit=64) or "RELATED_TO",
            })
        elif isinstance(e, dict):
            edge_label = e.get("relationship_name") or e.get("label") or "RELATED_TO"
            edges.append({
                "source": e.get("source", ""),
                "target": e.get("target", ""),
                "label": _short_text(edge_label, limit=64) or "RELATED_TO",
            })

    alias_decisions: dict[tuple[str, str], bool] | None = None
    if db is not None:
        try:
            alias_decisions = await _resolve_alias_merge_decisions_with_llm(
                nodes,
                db=db,
                model=alias_model,
            )
        except Exception:
            alias_decisions = None

    merged_nodes, merged_edges = _merge_alias_entities(
        nodes,
        edges,
        alias_decisions=alias_decisions,
    )
    pruned_nodes, pruned_edges = _prune_graph_for_preview(merged_nodes, merged_edges)
    return {"nodes": pruned_nodes, "edges": pruned_edges}


async def delete_dataset(
    project_id: str,
    *,
    model: str | None = None,
    embedding_model: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Delete a Cognee dataset (Cognee 0.5.3+ API)."""
    await _configure_cognee_llm(model=model, embedding_model=embedding_model, db=db)
    import cognee

    dataset_name = _dataset_name(project_id)
    datasets_api = getattr(cognee, "datasets", None)
    list_datasets_fn = getattr(datasets_api, "list_datasets", None)
    empty_dataset_fn = getattr(datasets_api, "empty_dataset", None)
    if not callable(list_datasets_fn) or not callable(empty_dataset_fn):
        raise RuntimeError("Cognee datasets API unavailable: require list_datasets and empty_dataset.")

    datasets = await list_datasets_fn()
    for dataset in datasets or []:
        dataset_id = getattr(dataset, "id", None)
        dataset_alias = str(getattr(dataset, "name", "") or "")
        if dataset_id is None:
            continue
        if dataset_alias == dataset_name:
            try:
                await empty_dataset_fn(dataset_id)
            except Exception as exc:
                message = str(exc or "")
                lowered = message.lower()
                sqlite_tree_overflow = (
                    ("expression tree is too large" in lowered and "sqlite" in lowered)
                    or ("maximum depth 1000" in lowered and "sqlite" in lowered)
                )
                if not sqlite_tree_overflow:
                    raise

                # Fallback for large datasets on SQLite backend:
                # bypass empty_dataset's wide OR cleanup query and delete dataset directly.
                from cognee.modules.data.methods import delete_dataset as delete_dataset_record

                await delete_dataset_record(dataset)
            return
    # Dataset already removed / inaccessible: treat as no-op.

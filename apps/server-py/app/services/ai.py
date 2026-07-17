import asyncio
import html
import json
import logging
import threading
import re
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Any, Awaitable, Callable

import litellm
litellm.drop_params = True  # vLLM/Qwen 兼容端点,丢弃底层不支持的参数(reasoning_effort 等)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import AIProviderConfig, PaymentConfig, PricingRule, PromptTemplate
from app.models.project import TextOperation, TextProject
from app.models.user import User
from app.redis import redis_client
from app.services.llm_runtime import (
    DEFAULT_LLM_OPENAI_API_STYLE,
    DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY,
    DEFAULT_LLM_PREFER_STREAM,
    DEFAULT_LLM_REASONING_EFFORT,
    DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_LLM_RETRY_COUNT,
    DEFAULT_LLM_RETRY_INTERVAL_SECONDS,
    DEFAULT_LLM_TASK_CONCURRENCY,
    coerce_limiter_limit,
    default_llm_runtime_config,
    model_supports_reasoning_effort,
    normalize_llm_runtime_config,
    normalize_model_concurrency_overrides,
    normalize_reasoning_effort,
)
from app.services.provider_models import (
    get_provider_chat_models,
    get_provider_embedding_models,
    get_provider_reranker_models,
)
from app.services.project_workspace import write_project_workspace_version_snapshot_from_db
from app.services.provider_type import is_anthropic_provider

logger = logging.getLogger(__name__)


OPERATION_PROMPTS = {
    "CREATE": "{input}",
    "CONTINUE": "{input}",
    "ANALYZE": "Analyze the text below.\n\n{input}",
    "REWRITE": "Rewrite the text below.\n\n{input}",
    "SUMMARIZE": "Summarize the text below.\n\n{input}",
}

DEFAULT_MODEL = ""
SUPPORTED_TEXT_OPERATION_TYPES = {"CREATE", "CONTINUE", "ANALYZE", "REWRITE", "SUMMARIZE"}
OPERATION_MAX_TOKENS = {"AGENT_SUGGEST": 2048, "AGENT_TASK": 16384}
DEFAULT_OPERATION_MAX_TOKENS = 4096
MONEY_SCALE = Decimal("0.000001")
SUPPORTED_LLM_PROVIDERS = {"openai_compatible", "anthropic_compatible"}

OPERATION_COMPONENT_KEYS = {
    "CREATE": "operation_create",
    "CONTINUE": "operation_continue",
    "ANALYZE": "operation_analyze",
    "REWRITE": "operation_rewrite",
    "SUMMARIZE": "operation_summarize",
    "AGENT_TASK": "operation_agent_task",
    "AGENT_SUGGEST": "operation_agent_suggest",
}

_LLM_BILLING_CONTEXT: ContextVar[dict[str, str | None] | None] = ContextVar(
    "llm_billing_context",
    default=None,
)
OperationProgressNotifier = Callable[[dict[str, Any]], Awaitable[None]]

_LLM_CONCURRENCY_LIMITERS: dict[tuple[str, int], asyncio.Semaphore] = {}
_LLM_CONCURRENCY_LIMITERS_LOCK = threading.Lock()
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TOOL_CALLING_ONLY_MODELS = {"ark-code-latest"}


def model_supports_structured_json(model: Any) -> bool:
    """Return whether a model may be used for strict JSON/graph extraction flows."""
    return str(model or "").strip().lower() not in _TOOL_CALLING_ONLY_MODELS


def require_structured_json_model(model: Any, usage: str) -> str:
    selected_model = str(model or "").strip()
    if not selected_model:
        raise RuntimeError(f"{usage} requires a configured model.")
    if not model_supports_structured_json(selected_model):
        raise RuntimeError(
            f"{usage} requires a model that supports structured JSON output; "
            f"{selected_model} is only supported for Agent tool-calling/write flows. "
            "Use a structured-capable model such as mimo for graph, memory, ontology, or planning tasks."
        )
    return selected_model


def _model_disables_json_response_format(model: Any) -> bool:
    return not model_supports_structured_json(model)


def _normalize_optional_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


@contextmanager
def llm_billing_scope(
    *,
    user_id: str | None,
    project_id: str | None = None,
    operation_id: str | None = None,
):
    token = _LLM_BILLING_CONTEXT.set(
        {
            "user_id": _normalize_optional_id(user_id),
            "project_id": _normalize_optional_id(project_id),
            "operation_id": _normalize_optional_id(operation_id),
        }
    )
    try:
        yield
    finally:
        _LLM_BILLING_CONTEXT.reset(token)


def _resolve_billing_context(
    *,
    billing_user_id: str | None = None,
    billing_project_id: str | None = None,
    billing_operation_id: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    scoped = _LLM_BILLING_CONTEXT.get() or {}
    user_id = _normalize_optional_id(billing_user_id) or _normalize_optional_id(scoped.get("user_id"))
    project_id = _normalize_optional_id(billing_project_id) or _normalize_optional_id(scoped.get("project_id"))
    operation_id = _normalize_optional_id(billing_operation_id) or _normalize_optional_id(scoped.get("operation_id"))
    return user_id, project_id, operation_id


def _resolve_llm_task_queue_key(
    *,
    billing_user_id: str | None = None,
    billing_project_id: str | None = None,
    billing_operation_id: str | None = None,
) -> str:
    user_id, project_id, operation_id = _resolve_billing_context(
        billing_user_id=billing_user_id,
        billing_project_id=billing_project_id,
        billing_operation_id=billing_operation_id,
    )
    if operation_id:
        return f"op:{operation_id}"
    if project_id:
        return f"project:{project_id}"
    if user_id:
        return f"user:{user_id}"
    return "global"

def _resolve_model_concurrency_limit(model: str, runtime_cfg: dict[str, Any]) -> int:
    fallback = coerce_limiter_limit(
        runtime_cfg.get("llm_model_default_concurrency", DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY),
        DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY,
    )
    overrides = normalize_model_concurrency_overrides(runtime_cfg.get("llm_model_concurrency_overrides"))
    return overrides.get(str(model or "").strip().lower(), fallback)


def _resolve_reasoning_effort(model: str, runtime_cfg: dict[str, Any]) -> str | None:
    if not model_supports_reasoning_effort(model):
        return None
    reasoning_effort = normalize_reasoning_effort(runtime_cfg.get("llm_reasoning_effort"))
    if reasoning_effort == DEFAULT_LLM_REASONING_EFFORT:
        return None
    if _is_deepseek_model(model) and reasoning_effort in {"none", "minimal"}:
        return None
    return reasoning_effort


def _get_concurrency_limiter(scope: str, *, limit: int) -> asyncio.Semaphore:
    safe_limit = coerce_limiter_limit(limit, 1)
    cache_key = (scope, safe_limit)
    with _LLM_CONCURRENCY_LIMITERS_LOCK:
        limiter = _LLM_CONCURRENCY_LIMITERS.get(cache_key)
        if limiter is None:
            limiter = asyncio.Semaphore(safe_limit)
            _LLM_CONCURRENCY_LIMITERS[cache_key] = limiter
    return limiter


@asynccontextmanager
async def _llm_concurrency_slot(
    *,
    task_key: str,
    task_limit: int,
    model: str,
    model_limit: int,
):
    task_limiter = _get_concurrency_limiter(f"task:{task_key}", limit=task_limit)
    model_limiter = _get_concurrency_limiter(f"model:{str(model or '').strip().lower()}", limit=model_limit)

    await task_limiter.acquire()
    try:
        await model_limiter.acquire()
        try:
            yield
        finally:
            model_limiter.release()
    finally:
        task_limiter.release()


def component_key_for_operation(op_type: str) -> str:
    key = OPERATION_COMPONENT_KEYS.get((op_type or "").upper())
    if key is None:
        raise ValueError(f"Unsupported operation type: {op_type!r}")
    return key


def resolve_component_model(
    project: TextProject | None,
    component_key: str,
    explicit_model: str | None = None,
    fallback_model: str = DEFAULT_MODEL,
) -> str:
    candidate = (explicit_model or "").strip()
    if candidate:
        return candidate

    component_models: dict[str, Any] = {}
    if project:
        project_component_models = getattr(project, "component_models", None)
        if isinstance(project_component_models, dict):
            component_models = project_component_models

    configured = component_models.get(component_key)
    # Phase C: per-role overrides. When resolving an operation_* key that
    # a sub-agent profile uses as its default_model_component, also check
    # the more specific ``role_<role>`` override first.
    if not configured and component_key.startswith("operation_"):
        role_override = _ROLE_OVERRIDE_FOR_COMPONENT.get(component_key)
        if role_override:
            role_value = component_models.get(role_override)
            if isinstance(role_value, str) and role_value.strip():
                return role_value.strip()
        configured = component_models.get("operation_default")

    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return fallback_model


# Phase C: map the operation_* component keys that sub-agent profiles use
# as ``default_model_component`` to the optional ``role_<role>`` override
# key. When a project sets role_writer in component_models, the writer /
# reviser profiles (which default to operation_continue) pick it up.
_ROLE_OVERRIDE_FOR_COMPONENT: dict[str, str] = {
    "operation_agent_task": "role_planner",   # planner/composer/updater/memory_builder/graph_extractor
    "operation_continue": "role_writer",       # writer / reviser
    "operation_analyze": "role_auditor",       # auditor / evaluator
    "operation_agent_suggest": "role_writer",  # suggest flows also benefit from writer-style model
}

resolve_explicit_component_model = resolve_component_model

async def get_available_models(db: AsyncSession) -> list[dict]:
    return await _collect_available_models(db, kind="chat")


async def get_available_embedding_models(db: AsyncSession) -> list[dict]:
    return await _collect_available_models(db, kind="embedding")


async def get_available_reranker_models(db: AsyncSession) -> list[dict]:
    return await _collect_available_models(db, kind="reranker")


async def _collect_available_models(db: AsyncSession, *, kind: str) -> list[dict]:
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.is_active == True)
    )
    providers = result.scalars().all()
    models = []
    seen: set[str] = set()
    for p in providers:
        if kind == "embedding":
            provider_models = get_provider_embedding_models(p)
        elif kind == "reranker":
            provider_models = get_provider_reranker_models(p)
        else:
            provider_models = get_provider_chat_models(p)
        for model_id in provider_models:
            if model_id in seen:
                continue
            seen.add(model_id)
            provider_name = str(getattr(p, "name", "") or getattr(p, "provider", "") or "").strip()
            models.append({"id": model_id, "provider": provider_name, "name": model_id})
    return models


async def get_prompt(
    op_type: str,
    input_text: str,
    db: AsyncSession,
    *,
    project: TextProject | None = None,
    character_context: str | None = None,
) -> str:
    normalized_op_type = (op_type or "").upper()
    project_prompts = getattr(project, "operation_prompts", None) if project is not None else None
    if isinstance(project_prompts, dict):
        project_template = project_prompts.get(normalized_op_type) or project_prompts.get(op_type)
        if isinstance(project_template, str) and project_template.strip():
            base_prompt = project_template.replace("{input}", input_text)
            context = str(character_context or "").strip()
            if not context:
                return base_prompt
            return f"{base_prompt}\n\n[Reference Cards]\n{context}"

    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.type == normalized_op_type, PromptTemplate.is_active == True
        )
    )
    template = result.scalar_one_or_none()
    base_prompt = ""
    if template:
        base_prompt = template.template.replace("{input}", input_text)
    else:
        base_prompt = OPERATION_PROMPTS.get(normalized_op_type, "{input}").replace("{input}", input_text)

    context = str(character_context or "").strip()
    if not context:
        return base_prompt
    return f"{base_prompt}\n\n[Reference Cards]\n{context}"


def _resolve_requested_model(model: str, configs: list[AIProviderConfig]) -> str:
    selected = str(model or "").strip()
    if selected:
        return selected

    for config in configs:
        for model_name in get_provider_chat_models(config):
            candidate = str(model_name or "").strip()
            if candidate:
                return candidate

    raise ValueError(
        "No model specified. Add chat models in Admin -> Providers or choose a model explicitly."
    )


def _usage_int(usage: Any, *keys: str) -> int:
    if usage is None:
        return 0
    for key in keys:
        value = None
        if isinstance(usage, dict):
            value = usage.get(key)
        else:
            value = getattr(usage, key, None)
        if value is None:
            continue
        try:
            parsed = int(value)
            if parsed >= 0:
                return parsed
        except (TypeError, ValueError):
            continue
    return 0


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(MONEY_SCALE)
    except Exception:
        return Decimal("0").quantize(MONEY_SCALE)


async def record_model_usage(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    db: AsyncSession,
    billing_user_id: str,
    billing_project_id: str | None = None,
    billing_operation_id: str | None = None,
    provider: str | None = None,
    request_id: str | None = None,
    source: str = "memory",
    metadata: dict[str, Any] | None = None,
) -> Decimal:
    """Record provider token usage for out-of-band LLM/embedding calls (e.g. cognee)."""
    from app.services.usage_records import create_usage_record

    _, cost = await create_usage_record(
        db=db,
        user_id=billing_user_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        project_id=billing_project_id,
        operation_id=billing_operation_id,
        provider=provider,
        request_id=request_id,
        source=source,
        metadata=metadata,
        deduct_balance=True,
    )
    return cost


def _normalize_response_schema_name(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return cleaned[:64] or "structured_output"


def _resolve_response_schema(
    response_schema: type[BaseModel] | dict[str, Any] | None,
    response_schema_name: str | None,
) -> tuple[str, dict[str, Any]] | None:
    if response_schema is None:
        return None
    if isinstance(response_schema, type) and issubclass(response_schema, BaseModel):
        return (
            _normalize_response_schema_name(response_schema_name or response_schema.__name__),
            response_schema.model_json_schema(),
        )
    if isinstance(response_schema, dict):
        return (
            _normalize_response_schema_name(response_schema_name or response_schema.get("title") or ""),
            response_schema,
        )
    raise TypeError("response_schema must be a pydantic model class or JSON schema dict")


def _is_deepseek_model(model: Any) -> bool:
    value = str(model or "").strip().lower()
    if "/" in value:
        _, value = value.split("/", 1)
    return value.startswith("deepseek")


def _resolve_json_schema_ref(root_schema: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = str(schema.get("$ref") or "")
    if not ref.startswith("#/$defs/"):
        return schema
    ref_name = ref.rsplit("/", 1)[-1]
    defs = root_schema.get("$defs")
    if isinstance(defs, dict) and isinstance(defs.get(ref_name), dict):
        return defs[ref_name]
    return schema


def _build_json_schema_example(schema: dict[str, Any], root_schema: dict[str, Any] | None = None, depth: int = 0) -> Any:
    if depth > 8:
        return None
    root = root_schema or schema
    current = _resolve_json_schema_ref(root, schema)
    if "const" in current:
        return current["const"]
    enum_values = current.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]
    schema_type = current.get("type")
    if schema_type == "object" or isinstance(current.get("properties"), dict):
        properties = current.get("properties") if isinstance(current.get("properties"), dict) else {}
        return {
            str(key): _build_json_schema_example(value, root, depth + 1)
            for key, value in properties.items()
            if isinstance(value, dict)
        }
    if schema_type == "array":
        items = current.get("items") if isinstance(current.get("items"), dict) else {}
        return [_build_json_schema_example(items, root, depth + 1)]
    if schema_type in {"integer", "number"}:
        return 1
    if schema_type == "boolean":
        return True
    return "string"


def _append_chat_json_schema_instruction(
    base_kwargs: dict[str, Any],
    schema_name: str,
    schema: dict[str, Any],
) -> None:
    messages = base_kwargs.get("messages")
    if not isinstance(messages, list) or not messages:
        return
    last_message = messages[-1]
    if not isinstance(last_message, dict):
        return
    content = str(last_message.get("content") or "")
    example_text = json.dumps(_build_json_schema_example(schema), ensure_ascii=False, indent=2)
    last_message["content"] = (
        f"{content}\n\n"
        "Return valid json only. Do not include markdown or commentary. "
        "The response must be a json object matching this example format.\n"
        f"Schema name: {schema_name}\n"
        f"EXAMPLE JSON OUTPUT:\n{example_text}"
    )


def _append_anthropic_json_schema_instruction(
    prompt: str,
    schema_name: str,
    schema: dict[str, Any],
) -> str:
    example_text = json.dumps(_build_json_schema_example(schema), ensure_ascii=False, indent=2)
    return (
        f"{prompt}\n\n"
        "Return valid json only. Do not include markdown or commentary. "
        "The response must be a json object matching this example format.\n"
        f"Schema name: {schema_name}\n"
        f"EXAMPLE JSON OUTPUT:\n{example_text}"
    )


def _apply_openai_response_schema(
    base_kwargs: dict[str, Any],
    *,
    openai_api_style: str,
    response_schema: tuple[str, dict[str, Any]] | None,
    model: Any = None,
) -> None:
    if response_schema is None:
        return
    schema_name, schema = response_schema
    # Schemas can opt out of strict json_schema mode (for gateways that reject
    # it) via the x_musegraph_response_format marker; the marker itself must
    # never reach the provider or the prompt.
    marker = ""
    if isinstance(schema, dict) and "x_musegraph_response_format" in schema:
        marker = str(schema.get("x_musegraph_response_format") or "").strip().lower()
        schema = {key: value for key, value in schema.items() if key != "x_musegraph_response_format"}
    force_json_object = marker == "json_object"
    prompt_only_json = _model_disables_json_response_format(model)
    if openai_api_style == "chat_completions":
        if prompt_only_json:
            _append_chat_json_schema_instruction(base_kwargs, schema_name, schema)
            return
        if force_json_object or _is_deepseek_model(model):
            base_kwargs["response_format"] = {"type": "json_object"}
            _append_chat_json_schema_instruction(base_kwargs, schema_name, schema)
            return
        base_kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        }
        return
    if prompt_only_json:
        base_kwargs["input"] = _append_anthropic_json_schema_instruction(
            str(base_kwargs.get("input") or ""), schema_name, schema
        )
        return
    if force_json_object:
        base_kwargs["text"] = {"format": {"type": "json_object"}}
        base_kwargs["input"] = _append_anthropic_json_schema_instruction(
            str(base_kwargs.get("input") or ""), schema_name, schema
        )
        return
    base_kwargs["text"] = {
        "format": {
            "type": "json_schema",
            "name": schema_name,
            "schema": schema,
            "strict": True,
        }
    }


async def _load_llm_runtime_config(db: AsyncSession | None) -> dict[str, Any]:
    defaults = default_llm_runtime_config()
    if db is None:
        return defaults
    try:
        result = await db.execute(select(PaymentConfig).where(PaymentConfig.type == "llm_runtime"))
        item = result.scalar_one_or_none()
        raw = item.config if item and isinstance(getattr(item, "config", None), dict) else None
        return normalize_llm_runtime_config(raw)
    except Exception:
        return defaults


def _extract_status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(exc, "response", None)
    if response is None:
        return None
    for attr in ("status_code", "status"):
        value = getattr(response, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _looks_like_html_error_message(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    if "<!doctype html" in text or "<html" in text or "<body" in text or "text/html" in text:
        return True
    return bool(_HTML_TAG_RE.search(text))


def _sanitize_provider_error_message(exc: Exception) -> str:
    status_code = _extract_status_code(exc)
    raw = str(exc or "").strip()
    if not raw:
        if status_code is not None:
            return f"Provider request failed with HTTP {status_code}"
        return f"{type(exc).__name__}: provider request failed"

    if not _looks_like_html_error_message(raw):
        return raw

    cleaned = html.unescape(_HTML_TAG_RE.sub(" ", raw))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if status_code is not None:
        if cleaned:
            return f"Provider returned HTTP {status_code}: {cleaned[:240]}"
        return f"Provider returned HTTP {status_code} with an HTML error page"
    if cleaned:
        return f"Provider returned an HTML error page: {cleaned[:240]}"
    return "Provider returned an HTML error page"


def _coerce_llm_exception(exc: Exception, *, error_context: str = "") -> Exception:
    sanitized = _sanitize_provider_error_message(exc)
    if not error_context:
        wrapped: Exception = RuntimeError(sanitized)
    else:
        wrapped = RuntimeError(f"LLM provider request failed ({error_context}): {sanitized}")
    status_code = _extract_status_code(exc)
    if status_code is not None:
        setattr(wrapped, "status_code", status_code)
    return wrapped


def _is_retryable_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    status_code = _extract_status_code(exc)
    if status_code is not None:
        if status_code != 200:
            return True
    if _looks_like_html_error_message(exc):
        return True
    # Unknown SDK/network exceptions are treated as transient by default.
    return status_code is None


async def _run_with_retry(
    request_factory: Callable[[], Awaitable[Any]],
    *,
    timeout_seconds: int,
    retry_count: int,
    retry_interval_seconds: float,
    error_context: str = "",
) -> Any:
    total_attempts = max(1, int(retry_count) + 1)
    last_exc: Exception | None = None
    for attempt in range(total_attempts):
        try:
            return await asyncio.wait_for(request_factory(), timeout=max(1, int(timeout_seconds)))
        except Exception as exc:
            last_exc = exc
            should_retry = attempt < (total_attempts - 1) and _is_retryable_llm_error(exc)
            if not should_retry:
                raise _coerce_llm_exception(exc, error_context=error_context) from exc
            await asyncio.sleep(max(0.0, float(retry_interval_seconds)))
    if last_exc is not None:
        raise _coerce_llm_exception(last_exc, error_context=error_context) from last_exc
    raise RuntimeError("LLM request failed without exception")


def _extract_openai_response_content(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text
    try:
        return str(response.choices[0].message.content or "")
    except Exception:
        return ""


def _extract_openai_response_usage(response: Any) -> tuple[int, int]:
    usage = response.usage if hasattr(response, "usage") else None
    input_tokens = _usage_int(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_int(usage, "output_tokens", "completion_tokens")
    return input_tokens, output_tokens


def _empty_llm_content_error(model: str, provider: str, provider_response_model: str = "") -> RuntimeError:
    detail = f'requested_model="{model}"'
    if provider:
        detail += f' provider="{provider}"'
    if provider_response_model:
        detail += f' provider_model="{provider_response_model}"'
    return RuntimeError(f"LLM returned empty content ({detail})")


async def _consume_openai_stream_response(
    stream: Any,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
    on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str, int, int]:
    content_parts: list[str] = []
    input_tokens = 0
    output_tokens = 0
    terminal_response: Any = None
    terminal_event_type = ""

    async def _push(text: str) -> None:
        content_parts.append(text)
        if on_delta is not None:
            try:
                await on_delta(text)
            except Exception:
                pass

    async for chunk in stream:
        event_type = str(getattr(chunk, "type", "") or "")
        if event_type == "response.output_text.delta":
            delta = getattr(chunk, "delta", None)
            if delta:
                await _push(str(delta))
            continue
        if event_type in {"response.completed", "response.failed", "response.incomplete"}:
            terminal_response = getattr(chunk, "response", None)
            terminal_event_type = event_type

        usage = chunk.usage if hasattr(chunk, "usage") else None
        input_tokens = max(input_tokens, _usage_int(usage, "input_tokens", "prompt_tokens"))
        output_tokens = max(output_tokens, _usage_int(usage, "output_tokens", "completion_tokens"))

        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        first = choices[0]
        delta = getattr(first, "delta", None)
        if delta is None and isinstance(first, dict):
            delta = first.get("delta")

        delta_content = getattr(delta, "content", None) if delta is not None else None
        if delta_content is None and isinstance(delta, dict):
            delta_content = delta.get("content")

        if isinstance(delta_content, str):
            if delta_content:
                await _push(delta_content)
            continue


        reasoning_content = getattr(delta, "reasoning_content", None) if delta is not None else None
        if reasoning_content is None and isinstance(delta, dict):
            reasoning_content = delta.get("reasoning_content") or delta.get("reasoning")
        if isinstance(reasoning_content, str) and reasoning_content:
            if on_thinking_delta is not None:
                try:
                    await on_thinking_delta(reasoning_content)
                except Exception:
                    pass
            continue
        if isinstance(delta_content, list):
            for part in delta_content:
                if isinstance(part, str):
                    if part:
                        await _push(part)
                    continue
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if text:
                        await _push(str(text))
                    continue
                text = getattr(part, "text", None) or getattr(part, "content", None)
                if text:
                    await _push(str(text))

    if terminal_response is not None:
        input_tokens, output_tokens = _extract_openai_response_usage(terminal_response)
        if terminal_event_type == "response.failed":
            error = getattr(terminal_response, "error", None)
            message = getattr(error, "message", None) or str(error or "OpenAI response failed")
            raise RuntimeError(message)
        if terminal_event_type == "response.incomplete":
            details = getattr(terminal_response, "incomplete_details", None)
            message = str(details or "OpenAI response incomplete")
            raise RuntimeError(message)
        if not content_parts:
            content = _extract_openai_response_content(terminal_response)
            if content:
                content_parts.append(content)

    return "".join(content_parts), input_tokens, output_tokens


async def call_llm(
    model: str,
    prompt: str,
    db: AsyncSession,
    max_tokens: int = 1024,
    *,
    billing_user_id: str | None = None,
    billing_project_id: str | None = None,
    billing_operation_id: str | None = None,
    prefer_stream_override: bool | None = None,
    minimum_timeout_seconds: int | None = None,
    response_schema: type[BaseModel] | dict[str, Any] | None = None,
    response_schema_name: str | None = None,
    stream_callback: Callable[[str], Awaitable[None]] | None = None,
    thinking_stream_callback: Callable[[str], Awaitable[None]] | None = None,
    reasoning_effort_override: str | None = None,
) -> dict:
    runtime_cfg = await _load_llm_runtime_config(db)
    timeout_seconds = int(runtime_cfg["llm_request_timeout_seconds"])
    if minimum_timeout_seconds is not None:
        timeout_seconds = max(
            timeout_seconds,
            max(5, min(1800, int(minimum_timeout_seconds))),
        )
    retry_count = int(runtime_cfg["llm_retry_count"])
    retry_interval_seconds = float(runtime_cfg["llm_retry_interval_seconds"])
    prefer_stream = bool(runtime_cfg.get("llm_prefer_stream", DEFAULT_LLM_PREFER_STREAM))
    if prefer_stream_override is not None:
        prefer_stream = bool(prefer_stream_override)
    task_concurrency_limit = coerce_limiter_limit(
        runtime_cfg.get("llm_task_concurrency", DEFAULT_LLM_TASK_CONCURRENCY),
        DEFAULT_LLM_TASK_CONCURRENCY,
    )
    openai_api_style = str(
        runtime_cfg.get("llm_openai_api_style", DEFAULT_LLM_OPENAI_API_STYLE)
        or DEFAULT_LLM_OPENAI_API_STYLE
    ).strip().lower()
    # Only models explicitly registered on an active provider are callable.
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.is_active == True)
    )
    configs = result.scalars().all()
    model = _resolve_requested_model(model, configs)

    config = None
    for c in configs:
        models = get_provider_chat_models(c)
        if model in models:
            config = c
            break

    if not config:
        raise ValueError(
            f'No active provider has registered model "{model}". Add the model in Admin -> Providers first.'
        )

    provider = str(config.provider).strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    resolved_response_schema = _resolve_response_schema(response_schema, response_schema_name)
    api_key = config.api_key
    base_url = config.base_url if config.base_url else None
    if not str(api_key or "").strip():
        raise ValueError(f'Provider "{config.name}" is missing an API key in Admin -> Providers.')

    content = ""
    input_tokens = 0
    output_tokens = 0
    provider_response_model = ""
    task_queue_key = _resolve_llm_task_queue_key(
        billing_user_id=billing_user_id,
        billing_project_id=billing_project_id,
        billing_operation_id=billing_operation_id,
    )
    model_concurrency_limit = _resolve_model_concurrency_limit(model, runtime_cfg)
    if reasoning_effort_override:
        reasoning_effort = reasoning_effort_override if model_supports_reasoning_effort(model) else None
    else:
        reasoning_effort = _resolve_reasoning_effort(model, runtime_cfg)

    routing_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        routing_kwargs["api_base"] = base_url

    try:
        async with _llm_concurrency_slot(
            task_key=task_queue_key,
            task_limit=task_concurrency_limit,
            model=model,
            model_limit=model_concurrency_limit,
        ):
            if is_anthropic_provider(provider):
                anthropic_prompt = prompt
                if resolved_response_schema is not None:
                    schema_name, schema = resolved_response_schema
                    anthropic_prompt = _append_anthropic_json_schema_instruction(prompt, schema_name, schema)
                anthropic_kwargs: dict[str, Any] = {
                    "model": model,
                    "max_tokens": max(64, int(max_tokens or 1024)),
                    "messages": [{"role": "user", "content": anthropic_prompt}],
                    "custom_llm_provider": "anthropic",
                    **routing_kwargs,
                }
                if _is_deepseek_model(model):
                    extra_body: dict[str, Any] = {"thinking": {"type": "enabled"}}
                    if reasoning_effort:
                        extra_body["output_config"] = {"effort": reasoning_effort}
                    anthropic_kwargs["extra_body"] = extra_body
                response = await _run_with_retry(
                    lambda: litellm.acompletion(**anthropic_kwargs),
                    timeout_seconds=timeout_seconds,
                    retry_count=retry_count,
                    retry_interval_seconds=retry_interval_seconds,
                    error_context=f'model="{model}", provider="{provider}"',
                )
                provider_response_model = str(getattr(response, "model", "") or "").strip()
                content = _extract_openai_response_content(response)
                input_tokens, output_tokens = _extract_openai_response_usage(response)
            else:
                if openai_api_style == "chat_completions":
                    base_kwargs = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max(64, int(max_tokens or 1024)),
                        "custom_llm_provider": "openai",
                        **routing_kwargs,
                    }
                    if _is_deepseek_model(model):
                        base_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                    if reasoning_effort:
                        base_kwargs["reasoning_effort"] = reasoning_effort
                    _apply_openai_response_schema(
                        base_kwargs,
                        openai_api_style=openai_api_style,
                        response_schema=resolved_response_schema,
                        model=model,
                    )
                    request_api = litellm.acompletion
                    stream_kwargs: dict[str, Any] = {"stream": True, "stream_options": {"include_usage": True}}
                else:
                    base_kwargs = {
                        "model": model,
                        "input": prompt,
                        "max_output_tokens": max(64, int(max_tokens or 1024)),
                        "custom_llm_provider": "openai",
                        **routing_kwargs,
                    }
                    if reasoning_effort:
                        base_kwargs["reasoning"] = {"effort": reasoning_effort}
                    _apply_openai_response_schema(
                        base_kwargs,
                        openai_api_style=openai_api_style,
                        response_schema=resolved_response_schema,
                        model=model,
                    )
                    request_api = litellm.aresponses
                    stream_kwargs = {"stream": True}

                async def _request_openai_nonstream() -> Any:
                    response = await request_api(**base_kwargs)
                    response_content = _extract_openai_response_content(response)
                    response_model = str(getattr(response, "model", "") or "").strip()
                    if not str(response_content or "").strip():
                        raise _empty_llm_content_error(model, provider, response_model)
                    response_input_tokens, response_output_tokens = _extract_openai_response_usage(response)
                    return response, response_content, response_input_tokens, response_output_tokens

                async def _request_openai_stream() -> tuple[str, int, int]:
                    response = await request_api(**base_kwargs, **stream_kwargs)
                    # Some gateways ignore stream=true and still return a regular completion object.
                    if hasattr(response, "__aiter__"):
                        stream_content, stream_input_tokens, stream_output_tokens = (
                            await _consume_openai_stream_response(response, on_delta=stream_callback, on_thinking_delta=thinking_stream_callback)
                        )
                    else:
                        stream_content = _extract_openai_response_content(response)
                        stream_input_tokens, stream_output_tokens = _extract_openai_response_usage(response)
                    if not str(stream_content or "").strip():
                        raise _empty_llm_content_error(model, provider)
                    return stream_content, stream_input_tokens, stream_output_tokens

                if prefer_stream:
                    content, input_tokens, output_tokens = await _run_with_retry(
                        _request_openai_stream,
                        timeout_seconds=timeout_seconds,
                        retry_count=retry_count,
                        retry_interval_seconds=retry_interval_seconds,
                        error_context=f'model="{model}", provider="{provider}"',
                    )
                else:
                    response, content, input_tokens, output_tokens = await _run_with_retry(
                        _request_openai_nonstream,
                        timeout_seconds=timeout_seconds,
                        retry_count=retry_count,
                        retry_interval_seconds=retry_interval_seconds,
                        error_context=f'model="{model}", provider="{provider}"',
                    )
                    provider_response_model = str(getattr(response, "model", "") or "").strip()

    except Exception:
        fallback_model = str(runtime_cfg.get("llm_fallback_model", "")).strip()
        if not fallback_model or fallback_model == model:
            raise
        logger.warning("LLM call failed for model=%s provider=%s, retrying with fallback=%s", model, provider, fallback_model)
        try:
            fallback_config = None
            for c in configs:
                fm_models = get_provider_chat_models(c)
                if fallback_model in fm_models:
                    fallback_config = c
                    break
            if not fallback_config:
                raise ValueError(f"Fallback model {fallback_model!r} not found in any active provider")
            fallback_provider = str(fallback_config.provider).strip().lower()
            fallback_api_key = fallback_config.api_key
            fallback_base_url = fallback_config.base_url if fallback_config.base_url else None
            if not str(fallback_api_key or "").strip():
                raise ValueError(f"Fallback provider {fallback_config.name!r} missing API key")
            fallback_kwargs: dict[str, Any] = {
                "model": fallback_model,
                "input": prompt,
                "max_output_tokens": max(64, int(max_tokens or 1024)),
                "custom_llm_provider": "openai",
                "api_key": fallback_api_key,
            }
            if fallback_base_url:
                fallback_kwargs["api_base"] = fallback_base_url
            if reasoning_effort:
                fallback_kwargs["reasoning"] = {"effort": reasoning_effort}
            fallback_response = await litellm.aresponses(**fallback_kwargs)
            content = str(_extract_openai_response_content(fallback_response) or "")
            fallback_input_tokens, fallback_output_tokens = _extract_openai_response_usage(fallback_response)
            input_tokens = fallback_input_tokens
            output_tokens = fallback_output_tokens
            provider_response_model = str(getattr(fallback_response, "model", "") or "")
            provider = fallback_provider
            model = fallback_model
            logger.info("Fallback succeeded with model=%s provider=%s tokens_in=%d tokens_out=%d", model, provider, input_tokens, output_tokens)
        except Exception:
            logger.exception("Fallback also failed for model=%s", fallback_model)
            raise


    if not str(content or "").strip():
        raise _empty_llm_content_error(model, provider, provider_response_model)

    usage_user_id, usage_project_id, usage_operation_id = _resolve_billing_context(
        billing_user_id=billing_user_id,
        billing_project_id=billing_project_id,
        billing_operation_id=billing_operation_id,
    )
    if usage_user_id:
        cost = await calculate_cost(model, input_tokens, output_tokens, db)
    else:
        cost = _money(0)

    usage_recorded = False
    if usage_user_id:
        from app.services.usage_records import create_usage_record, resolve_billing_mode

        user_result = await db.execute(select(User).where(User.id == usage_user_id))
        usage_user = user_result.scalar_one_or_none()
        if not usage_user:
            raise ValueError("Billing user not found")

        billing_mode = await resolve_billing_mode(model, db)
        await create_usage_record(
            db=db,
            user_id=usage_user.id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            project_id=usage_project_id,
            operation_id=usage_operation_id,
            provider=provider,
            billing_mode=billing_mode,
            source="llm",
            deduct_balance=True,
            user_balance_holder=usage_user,
        )
        usage_recorded = True

    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "provider": provider,
        "model": model,
        "cost": cost,
        "usage_recorded": usage_recorded,
    }


async def calculate_cost(
    model: str, input_tokens: int, output_tokens: int, db: AsyncSession
) -> Decimal:
    safe_input_tokens = max(0, int(input_tokens or 0))
    safe_output_tokens = max(0, int(output_tokens or 0))
    result = await db.execute(
        select(PricingRule).where(
            PricingRule.model == model, PricingRule.is_active == True
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return _money(0)
    billing_mode = str(getattr(rule, "billing_mode", "TOKEN") or "TOKEN").upper()
    if billing_mode == "REQUEST":
        return _money(getattr(rule, "request_price", 0) or 0)

    token_unit = int(getattr(rule, "token_unit", 1_000_000) or 1_000_000)
    if token_unit <= 0:
        token_unit = 1_000_000
    cost = (
        Decimal(str(rule.input_price or 0)) * safe_input_tokens / token_unit
        + Decimal(str(rule.output_price or 0)) * safe_output_tokens / token_unit
    )
    return _money(cost)


async def _notify_operation_progress(
    notifier: OperationProgressNotifier | None,
    *,
    progress: int,
    status: str,
    message: str,
    output: str | None = None,
) -> None:
    if not notifier:
        return
    payload: dict[str, Any] = {
        "progress": int(progress),
        "status": status,
        "message": message,
    }
    if output is not None:
        payload["output"] = output
    try:
        await notifier(payload)
    except Exception:
        return


async def _persist_operation_state(db: AsyncSession, *, commit_progress: bool) -> None:
    await db.flush()
    if commit_progress:
        await db.commit()


async def _apply_operation_usage(
    *,
    llm_result: dict[str, Any],
    requested_model: str,
    operation: TextOperation,
    project: TextProject,
    user: User,
    db: AsyncSession,
) -> Decimal:
    model_name = str(llm_result.get("model") or requested_model or DEFAULT_MODEL).strip() or "unknown"
    cost = llm_result.get("cost")
    if cost is None:
        cost = await calculate_cost(
            model_name, llm_result["input_tokens"], llm_result["output_tokens"], db
        )
    cost = _money(cost)
    usage_recorded = bool(llm_result.get("usage_recorded"))
    operation_cost = cost

    if not usage_recorded:
        from app.services.usage_records import create_usage_record, resolve_billing_mode

        await create_usage_record(
            db=db,
            user_id=user.id,
            model=model_name,
            input_tokens=llm_result["input_tokens"],
            output_tokens=llm_result["output_tokens"],
            cost=cost,
            project_id=project.id,
            operation_id=operation.id,
            provider=str(llm_result.get("provider") or "") or None,
            billing_mode=await resolve_billing_mode(model_name, db),
            source="operation",
            deduct_balance=True,
            user_balance_holder=user,
        )
    return operation_cost


# Top-level payload keys mirrored into the project's agent workspace state.
AGENT_WORKSPACE_KEYS = (
    "task_kind",
    "text_type",
    "memory_schema",
    "structured_memory",
    "retrieval_queries",
    "writing_plan",
    "next_actions",
)


def _parse_agent_payload(content: str) -> dict[str, Any] | None:
    text = str(content or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _compact_agent_task(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Strip bulky document content from the payload before storing it in the workspace."""
    compacted = {key: value for key, value in payload.items() if key != "content"}
    content = payload.get("content")
    if isinstance(content, str):
        compacted["content_chars"] = len(content)
        return compacted, True
    return compacted, False


async def _finalize_agent_operation(
    *,
    operation: TextOperation,
    project: TextProject,
    op_type: str,
    input_text: str,
    content: str,
    db: AsyncSession,
) -> None:
    raw_metadata = getattr(operation, "metadata_", None)
    # Re-assign fresh dicts so SQLAlchemy JSON columns register the mutation.
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    payload = _parse_agent_payload(content)

    if payload is None:
        metadata["agent_state_update"] = {"raw_output_only": True}
        operation.metadata_ = metadata
        return

    raw_state = getattr(project, "creative_state", None)
    creative_state = dict(raw_state) if isinstance(raw_state, dict) else {}
    raw_workspace = creative_state.get("agent_workspace")
    workspace = dict(raw_workspace) if isinstance(raw_workspace, dict) else {}
    for key in AGENT_WORKSPACE_KEYS:
        if key in payload:
            workspace[key] = payload[key]

    last_task, workspace_compacted = _compact_agent_task(payload)
    workspace["last_task"] = last_task
    if "content" in payload or "unit_title" in payload:
        workspace["last_document_unit"] = last_task

    creative_state["agent_workspace"] = workspace
    project.creative_state = creative_state
    metadata["agent_state_update"] = {
        "raw_output_only": False,
        "workspace_compacted": workspace_compacted,
    }

    writeback_mode = str(metadata.get("agent_memory_writeback_mode") or "").strip()
    if op_type == "AGENT_TASK":
        if writeback_mode == "workspace_only":
            skip_info: dict[str, Any] = {"mode": "workspace_only", "skipped": True}
            reason = str(metadata.get("agent_memory_writeback_reason") or "").strip()
            if reason:
                skip_info["reason"] = reason
            metadata["agent_memory_writeback"] = skip_info
        else:
            from app.services import memory_backend

            try:
                writeback_result = await memory_backend.writeback_agent(
                    project.id,
                    payload,
                    operation_id=operation.id,
                    operation_type=op_type,
                    source_text=input_text,
                    db=db,
                    project=project,
                )
                metadata["agent_memory_writeback"] = writeback_result
            except Exception as exc:
                logger.exception("Agent memory writeback failed for project=%s", project.id)
                metadata["agent_memory_writeback"] = {"error": str(exc)}

    operation.metadata_ = metadata

    try:
        await write_project_workspace_version_snapshot_from_db(
            project, db, f"Apply {op_type} result"
        )
    except Exception:
        logger.exception("Workspace snapshot failed for project=%s", project.id)


async def run_operation(
    operation_id: str,
    project: TextProject,
    user: User,
    op_type: str,
    input_text: str,
    model: str,
    db: AsyncSession,
    progress_notifier: OperationProgressNotifier | None = None,
    loaded_operation: TextOperation | None = None,
    use_rag: bool = True,
    character_context: str | None = None,
    reference_cards: dict[str, Any] | None = None,
    commit_progress: bool = False,
) -> TextOperation:
    operation = loaded_operation
    if operation is None:
        result = await db.execute(
            select(TextOperation).where(TextOperation.id == operation_id)
        )
        operation = result.scalar_one()

    try:
        operation.status = "PROCESSING"
        operation.progress = 10
        operation.message = "Preparing prompt..."
        await _persist_operation_state(db, commit_progress=commit_progress)
        await _notify_operation_progress(
            progress_notifier,
            progress=10,
            status="PROCESSING",
            message="Preparing prompt...",
        )

        prompt = await get_prompt(
            op_type,
            input_text or "",
            db,
            project=project,
            character_context=character_context,
        )

        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
            operation_id=operation.id,
        ):
            project_memory_id = str(getattr(project, "memory_id", "") or "").strip()
            if use_rag and (op_type != "CREATE" or project_memory_id):
                # Enhance the prompt with the project's creative memory pack
                # (structured state + cognee retrieval context).
                from app.services import creative_memory

                memory_pack = await creative_memory.build_creative_memory_pack(
                    project=project,
                    project_id=project.id,
                    op_type=op_type,
                    input_text=input_text or "",
                    db=db,
                    reference_cards=reference_cards,
                )
                memory_block = creative_memory.render_creative_memory_block(memory_pack)
                if str(memory_block or "").strip():
                    prompt = (
                        f"{prompt}\n\n"
                        f"{memory_block}\n\n"
                        "Use the Creative Memory Context as the authoritative project memory for this operation. "
                        "Follow the type-specific execution rules and the retrieved constraints before producing the final output."
                    )

            operation.progress = 30
            operation.message = "Calling AI model..."
            await _persist_operation_state(db, commit_progress=commit_progress)
            await _notify_operation_progress(
                progress_notifier,
                progress=30,
                status="PROCESSING",
                message="Calling AI model...",
            )

            llm_result = await call_llm(
                model,
                prompt,
                db,
                max_tokens=OPERATION_MAX_TOKENS.get(op_type, DEFAULT_OPERATION_MAX_TOKENS),
            )

        operation.progress = 80
        operation.message = "Processing result..."
        await _persist_operation_state(db, commit_progress=commit_progress)
        await _notify_operation_progress(
            progress_notifier,
            progress=80,
            status="PROCESSING",
            message="Processing result...",
        )

        operation_cost = await _apply_operation_usage(
            llm_result=llm_result,
            requested_model=model,
            operation=operation,
            project=project,
            user=user,
            db=db,
        )

        operation.output = llm_result["content"]
        operation.input_tokens = llm_result["input_tokens"]
        operation.output_tokens = llm_result["output_tokens"]
        operation.cost = operation_cost

        if op_type in {"AGENT_TASK", "AGENT_SUGGEST"}:
            await _finalize_agent_operation(
                operation=operation,
                project=project,
                op_type=op_type,
                input_text=input_text or "",
                content=str(llm_result.get("content") or ""),
                db=db,
            )

        operation.status = "COMPLETED"
        operation.progress = 100
        operation.message = "Done"
        await _persist_operation_state(db, commit_progress=commit_progress)
        await _notify_operation_progress(
            progress_notifier,
            progress=100,
            status="COMPLETED",
            message="Done",
            output=llm_result.get("content"),
        )

    except Exception as e:
        operation.status = "FAILED"
        operation.error = str(e)
        operation.progress = 0
        operation.message = "Failed"
        await _persist_operation_state(db, commit_progress=commit_progress)
        await _notify_operation_progress(
            progress_notifier,
            progress=0,
            status="FAILED",
            message=str(e),
        )

    return operation


async def run_operation_async(
    operation_id: str,
    project_id: str,
    user_id: str,
    op_type: str,
    input_text: str | None,
    model: str,
    use_rag: bool = True,
    character_context: str | None = None,
    reference_cards: dict[str, Any] | None = None,
):
    """Run operation in background and publish progress via Redis."""
    from app.database import async_session

    async with async_session() as db:
        operation = None
        try:
            result = await db.execute(
                select(TextOperation).where(TextOperation.id == operation_id)
            )
            operation = result.scalar_one()
            result = await db.execute(
                select(TextProject).where(TextProject.id == project_id)
            )
            project = result.scalar_one()
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one()

            channel = f"operation:{operation_id}"
            async def _redis_notifier(payload: dict[str, Any]) -> None:
                await redis_client.publish(channel, json.dumps(payload))

            await run_operation(
                operation_id=operation_id,
                project=project,
                user=user,
                op_type=op_type,
                input_text=input_text or "",
                model=model,
                db=db,
                progress_notifier=_redis_notifier,
                loaded_operation=operation,
                use_rag=use_rag,
                character_context=character_context,
                reference_cards=reference_cards,
                commit_progress=True,
            )
            await db.commit()
        except Exception as e:
            if operation is not None:
                operation.status = "FAILED"
                operation.error = str(e)
                operation.progress = 0
                operation.message = "Failed"
            await db.commit()
            await redis_client.publish(
                f"operation:{operation_id}",
                json.dumps({
                    "progress": 0,
                    "status": "FAILED",
                    "message": str(e),
                }),
            )

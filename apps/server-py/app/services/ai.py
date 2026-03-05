import asyncio
import json
import threading
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import Usage
from app.models.config import AIProviderConfig, PaymentConfig, PricingRule, PromptTemplate
from app.models.project import TextOperation, TextProject
from app.models.user import User
from app.redis import redis_client
from app.services.provider_models import get_provider_chat_models, get_provider_embedding_models, get_provider_models
from app.services.provider_type import is_anthropic_provider


OPERATION_PROMPTS = {
    "CREATE": "You are a creative writing assistant. Based on the following prompt, create original content:\n\n{input}",
    "CONTINUE": "You are a creative writing assistant. Continue the following text naturally:\n\n{input}",
    "ANALYZE": "You are a text analysis expert. Analyze the following text in detail:\n\n{input}",
    "REWRITE": "You are a professional editor. Rewrite the following text to improve clarity and style:\n\n{input}",
    "SUMMARIZE": "You are a summarization expert. Provide a concise summary of the following text:\n\n{input}",
}

DEFAULT_MODEL = str(settings.LLM_MODEL or "").strip()
MONEY_SCALE = Decimal("0.000001")
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 180
DEFAULT_LLM_RETRY_COUNT = 4
DEFAULT_LLM_RETRY_INTERVAL_SECONDS = 2.0
DEFAULT_LLM_PREFER_STREAM = True
DEFAULT_LLM_STREAM_FALLBACK_NONSTREAM = True
DEFAULT_LLM_TASK_CONCURRENCY = 1
DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY = 8
SUPPORTED_LLM_PROVIDERS = {"openai_compatible", "anthropic_compatible"}

OPERATION_COMPONENT_KEYS = {
    "CREATE": "operation_create",
    "CONTINUE": "operation_continue",
    "ANALYZE": "operation_analyze",
    "REWRITE": "operation_rewrite",
    "SUMMARIZE": "operation_summarize",
}

_LLM_BILLING_CONTEXT: ContextVar[dict[str, str | None] | None] = ContextVar(
    "llm_billing_context",
    default=None,
)
OperationProgressNotifier = Callable[[dict[str, Any]], Awaitable[None]]

_LLM_CONCURRENCY_LIMITERS: dict[tuple[str, int], asyncio.Semaphore] = {}
_LLM_CONCURRENCY_LIMITERS_LOCK = threading.Lock()


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


def _coerce_limiter_limit(value: Any, default: int) -> int:
    try:
        return max(1, min(64, int(value)))
    except (TypeError, ValueError):
        return max(1, min(64, int(default)))


def _parse_model_concurrency_overrides(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in raw.items():
        model_name = str(key or "").strip().lower()
        if not model_name:
            continue
        normalized[model_name] = _coerce_limiter_limit(value, DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY)
    return normalized


def _resolve_model_concurrency_limit(model: str, runtime_cfg: dict[str, Any]) -> int:
    fallback = _coerce_limiter_limit(
        runtime_cfg.get("llm_model_default_concurrency", DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY),
        DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY,
    )
    overrides = _parse_model_concurrency_overrides(runtime_cfg.get("llm_model_concurrency_overrides"))
    return overrides.get(str(model or "").strip().lower(), fallback)


def _get_concurrency_limiter(scope: str, *, limit: int) -> asyncio.Semaphore:
    safe_limit = _coerce_limiter_limit(limit, 1)
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
    return OPERATION_COMPONENT_KEYS.get((op_type or "").upper(), "operation_default")


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
    if not configured and component_key.startswith("operation_"):
        configured = component_models.get("operation_default")
    if not configured:
        configured = component_models.get("default")

    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return fallback_model


async def get_available_models(db: AsyncSession) -> list[dict]:
    return await _collect_available_models(db, kind="chat")


async def get_available_embedding_models(db: AsyncSession) -> list[dict]:
    return await _collect_available_models(db, kind="embedding")


async def _collect_available_models(db: AsyncSession, *, kind: str) -> list[dict]:
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.is_active == True)
    )
    providers = result.scalars().all()
    models = []
    seen: set[str] = set()
    for p in providers:
        provider_models = get_provider_models(p, "embedding" if kind == "embedding" else "chat")
        for model_id in provider_models:
            if model_id in seen:
                continue
            seen.add(model_id)
            models.append({"id": model_id, "provider": p.provider, "name": model_id})
    return models


async def get_prompt(
    op_type: str,
    input_text: str,
    db: AsyncSession,
    *,
    character_context: str | None = None,
) -> str:
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.type == op_type, PromptTemplate.is_active == True
        )
    )
    template = result.scalar_one_or_none()
    base_prompt = ""
    if template:
        base_prompt = template.template.replace("{input}", input_text)
    else:
        base_prompt = OPERATION_PROMPTS.get(op_type, "{input}").replace("{input}", input_text)

    context = str(character_context or "").strip()
    if not context:
        return base_prompt
    return (
        f"{base_prompt}\n\n"
        "## Reference Cards\n"
        "Use the following cards as hard constraints for consistency:\n"
        f"{context}"
    )


def detect_provider(model: str) -> str:
    normalized = str(model or "").strip().lower()
    if not normalized:
        return "openai_compatible"

    if "/" in normalized:
        prefix = normalized.split("/", 1)[0]
        if prefix in {"anthropic", "claude"}:
            return "anthropic_compatible"
        if prefix in {"openai", "gpt", "o1", "o3"}:
            return "openai_compatible"

    if normalized.startswith("gpt") or normalized.startswith("o1") or normalized.startswith("o3"):
        return "openai_compatible"
    if normalized.startswith("claude"):
        return "anthropic_compatible"
    return "openai_compatible"


def _resolve_requested_model(model: str, configs: list[AIProviderConfig]) -> str:
    selected = str(model or "").strip()
    if selected:
        return selected
    if DEFAULT_MODEL:
        return DEFAULT_MODEL

    for config in configs:
        for model_name in get_provider_chat_models(config):
            candidate = str(model_name or "").strip()
            if candidate:
                return candidate

    raise ValueError(
        "No model specified. Please provide `model`, set LLM_MODEL, or configure provider chat models in WebUI."
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


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _default_llm_runtime_config() -> dict[str, Any]:
    return {
        "llm_request_timeout_seconds": int(DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS),
        "llm_retry_count": int(DEFAULT_LLM_RETRY_COUNT),
        "llm_retry_interval_seconds": float(DEFAULT_LLM_RETRY_INTERVAL_SECONDS),
        "llm_prefer_stream": bool(DEFAULT_LLM_PREFER_STREAM),
        "llm_stream_fallback_nonstream": bool(DEFAULT_LLM_STREAM_FALLBACK_NONSTREAM),
        "llm_task_concurrency": int(DEFAULT_LLM_TASK_CONCURRENCY),
        "llm_model_default_concurrency": int(DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY),
        "llm_model_concurrency_overrides": {},
    }


def _normalize_llm_runtime_config(raw: Any) -> dict[str, Any]:
    payload = _default_llm_runtime_config()
    current = raw if isinstance(raw, dict) else {}
    try:
        payload["llm_request_timeout_seconds"] = max(
            5,
            min(1800, int(current.get("llm_request_timeout_seconds", payload["llm_request_timeout_seconds"]))),
        )
    except (TypeError, ValueError):
        pass
    try:
        payload["llm_retry_count"] = max(
            0,
            min(10, int(current.get("llm_retry_count", payload["llm_retry_count"]))),
        )
    except (TypeError, ValueError):
        pass
    try:
        payload["llm_retry_interval_seconds"] = max(
            0.0,
            min(60.0, float(current.get("llm_retry_interval_seconds", payload["llm_retry_interval_seconds"]))),
        )
    except (TypeError, ValueError):
        pass
    payload["llm_prefer_stream"] = _coerce_bool(
        current.get("llm_prefer_stream", payload["llm_prefer_stream"]),
        bool(payload["llm_prefer_stream"]),
    )
    payload["llm_stream_fallback_nonstream"] = _coerce_bool(
        current.get("llm_stream_fallback_nonstream", payload["llm_stream_fallback_nonstream"]),
        bool(payload["llm_stream_fallback_nonstream"]),
    )
    payload["llm_task_concurrency"] = _coerce_limiter_limit(
        current.get("llm_task_concurrency", payload["llm_task_concurrency"]),
        int(payload["llm_task_concurrency"]),
    )
    payload["llm_model_default_concurrency"] = _coerce_limiter_limit(
        current.get("llm_model_default_concurrency", payload["llm_model_default_concurrency"]),
        int(payload["llm_model_default_concurrency"]),
    )
    payload["llm_model_concurrency_overrides"] = _parse_model_concurrency_overrides(
        current.get("llm_model_concurrency_overrides")
    )
    return payload


async def _load_llm_runtime_config(db: AsyncSession | None) -> dict[str, Any]:
    defaults = _default_llm_runtime_config()
    if db is None:
        return defaults
    try:
        result = await db.execute(select(PaymentConfig).where(PaymentConfig.type == "oasis"))
        item = result.scalar_one_or_none()
        raw = item.config if item and isinstance(getattr(item, "config", None), dict) else None
        return _normalize_llm_runtime_config(raw)
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


def _is_retryable_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    status_code = _extract_status_code(exc)
    if status_code is None:
        # Unknown SDK/network exceptions are treated as transient by default.
        return True
    if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
        return True
    if 500 <= status_code <= 599:
        return True
    return False


async def _run_with_retry(
    request_factory: Callable[[], Awaitable[Any]],
    *,
    timeout_seconds: int,
    retry_count: int,
    retry_interval_seconds: float,
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
                raise
            await asyncio.sleep(max(0.0, float(retry_interval_seconds)))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM request failed without exception")


def _extract_openai_response_content(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except Exception:
        return ""


def _extract_openai_response_usage(response: Any) -> tuple[int, int]:
    usage = response.usage if hasattr(response, "usage") else None
    input_tokens = _usage_int(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_int(usage, "output_tokens", "completion_tokens")
    return input_tokens, output_tokens


async def _consume_openai_stream_response(stream: Any) -> tuple[str, int, int]:
    content_parts: list[str] = []
    input_tokens = 0
    output_tokens = 0

    async for chunk in stream:
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
                content_parts.append(delta_content)
            continue

        if isinstance(delta_content, list):
            for part in delta_content:
                if isinstance(part, str):
                    if part:
                        content_parts.append(part)
                    continue
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if text:
                        content_parts.append(str(text))
                    continue
                text = getattr(part, "text", None) or getattr(part, "content", None)
                if text:
                    content_parts.append(str(text))

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
) -> dict:
    runtime_cfg = await _load_llm_runtime_config(db)
    timeout_seconds = int(runtime_cfg["llm_request_timeout_seconds"])
    retry_count = int(runtime_cfg["llm_retry_count"])
    retry_interval_seconds = float(runtime_cfg["llm_retry_interval_seconds"])
    prefer_stream = bool(runtime_cfg.get("llm_prefer_stream", DEFAULT_LLM_PREFER_STREAM))
    stream_fallback_nonstream = bool(
        runtime_cfg.get("llm_stream_fallback_nonstream", DEFAULT_LLM_STREAM_FALLBACK_NONSTREAM)
    )
    task_concurrency_limit = _coerce_limiter_limit(
        runtime_cfg.get("llm_task_concurrency", DEFAULT_LLM_TASK_CONCURRENCY),
        DEFAULT_LLM_TASK_CONCURRENCY,
    )
    # First try to find a provider config that has this model in its chat-model list
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
        # Fall back to provider detection by model name prefix
        provider = detect_provider(model)
        for c in configs:
            if c.provider == provider:
                config = c
                break

    provider = str(config.provider if config else detect_provider(model)).strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    api_key = config.api_key if config else (
        settings.ANTHROPIC_API_KEY if is_anthropic_provider(provider) else (settings.OPENAI_API_KEY or settings.LLM_API_KEY)
    )
    base_url = config.base_url if config and config.base_url else None
    if not str(api_key or "").strip():
        raise ValueError(f"Missing API key for provider: {provider}")

    content = ""
    input_tokens = 0
    output_tokens = 0
    task_queue_key = _resolve_llm_task_queue_key(
        billing_user_id=billing_user_id,
        billing_project_id=billing_project_id,
        billing_operation_id=billing_operation_id,
    )
    model_concurrency_limit = _resolve_model_concurrency_limit(model, runtime_cfg)

    async with _llm_concurrency_slot(
        task_key=task_queue_key,
        task_limit=task_concurrency_limit,
        model=model,
        model_limit=model_concurrency_limit,
    ):
        if is_anthropic_provider(provider):
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url or None)
            response = await _run_with_retry(
                lambda: client.messages.create(
                    model=model,
                    max_tokens=max(64, int(max_tokens or 1024)),
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout_seconds=timeout_seconds,
                retry_count=retry_count,
                retry_interval_seconds=retry_interval_seconds,
            )
            usage = response.usage if hasattr(response, "usage") else None
            content = str(response.content[0].text or "")
            input_tokens = _usage_int(usage, "input_tokens", "prompt_tokens")
            output_tokens = _usage_int(usage, "output_tokens", "completion_tokens")
        else:
            import openai
            client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
            base_kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max(64, int(max_tokens or 1024)),
            }

            async def _request_openai_nonstream() -> Any:
                return await client.chat.completions.create(**base_kwargs)

            async def _request_openai_stream() -> tuple[str, int, int]:
                response = await client.chat.completions.create(
                    **base_kwargs,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                # Some gateways ignore stream=true and still return a regular completion object.
                if hasattr(response, "__aiter__"):
                    return await _consume_openai_stream_response(response)
                fallback_content = _extract_openai_response_content(response)
                fallback_input_tokens, fallback_output_tokens = _extract_openai_response_usage(response)
                return fallback_content, fallback_input_tokens, fallback_output_tokens

            if prefer_stream:
                try:
                    stream_content, stream_input_tokens, stream_output_tokens = await _run_with_retry(
                        _request_openai_stream,
                        timeout_seconds=timeout_seconds,
                        retry_count=retry_count,
                        retry_interval_seconds=retry_interval_seconds,
                    )
                    content = stream_content
                    input_tokens = stream_input_tokens
                    output_tokens = stream_output_tokens
                except Exception:
                    if not stream_fallback_nonstream:
                        raise
                    response = await _run_with_retry(
                        _request_openai_nonstream,
                        timeout_seconds=timeout_seconds,
                        retry_count=retry_count,
                        retry_interval_seconds=retry_interval_seconds,
                    )
                    content = _extract_openai_response_content(response)
                    input_tokens, output_tokens = _extract_openai_response_usage(response)
            else:
                response = await _run_with_retry(
                    _request_openai_nonstream,
                    timeout_seconds=timeout_seconds,
                    retry_count=retry_count,
                    retry_interval_seconds=retry_interval_seconds,
                )
                content = _extract_openai_response_content(response)
                input_tokens, output_tokens = _extract_openai_response_usage(response)

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
        user_result = await db.execute(
            select(User).where(User.id == usage_user_id)
        )
        usage_user = user_result.scalar_one_or_none()
        if not usage_user:
            raise ValueError("Billing user not found")

        current_balance = _money(usage_user.balance)
        next_balance = _money(current_balance - cost)
        if next_balance < Decimal("0"):
            raise ValueError("Insufficient balance")
        usage_user.balance = next_balance

        usage = Usage(
            user_id=usage_user.id,
            project_id=usage_project_id,
            operation_id=usage_operation_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )
        db.add(usage)
        await db.flush()
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
        # Compatibility fallback for mocked/legacy call_llm implementations.
        current_balance = _money(user.balance)
        next_balance = _money(current_balance - cost)
        if next_balance < Decimal("0"):
            raise ValueError("Insufficient balance")
        user.balance = next_balance
        usage = Usage(
            user_id=user.id,
            project_id=project.id,
            operation_id=operation.id,
            model=model_name,
            input_tokens=llm_result["input_tokens"],
            output_tokens=llm_result["output_tokens"],
            cost=cost,
        )
        db.add(usage)
        await db.flush()
    else:
        operation_cost_row = await db.execute(
            select(func.coalesce(func.sum(Usage.cost), 0)).where(Usage.operation_id == operation.id)
        )
        operation_cost = _money(operation_cost_row.scalar() or 0)
    return operation_cost


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
        await db.flush()
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
            character_context=character_context,
        )

        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
            operation_id=operation.id,
        ):
            if use_rag:
                # Enhance with knowledge graph prediction for CONTINUE/CREATE.
                try:
                    from app.services.prediction import get_enhanced_prompt
                    prompt = await get_enhanced_prompt(
                        project.id,
                        op_type,
                        input_text or "",
                        prompt,
                        db,
                        reference_cards=reference_cards,
                    )
                except Exception:
                    pass  # Fall back to base prompt

            operation.progress = 30
            operation.message = "Calling AI model..."
            await db.flush()
            await _notify_operation_progress(
                progress_notifier,
                progress=30,
                status="PROCESSING",
                message="Calling AI model...",
            )

            llm_result = await call_llm(model, prompt, db)

        operation.progress = 80
        operation.message = "Processing result..."
        await db.flush()
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
        operation.status = "COMPLETED"
        operation.progress = 100
        operation.message = "Done"
        await db.flush()
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
        await db.flush()
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

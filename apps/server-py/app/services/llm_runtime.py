from typing import Any


DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 180
DEFAULT_LLM_RETRY_COUNT = 4
DEFAULT_LLM_RETRY_INTERVAL_SECONDS = 2.0
DEFAULT_LLM_PREFER_STREAM = True
DEFAULT_LLM_STREAM_FALLBACK_NONSTREAM = True
DEFAULT_LLM_OPENAI_API_STYLE = "responses"
DEFAULT_LLM_TASK_CONCURRENCY = 4
DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY = 8
DEFAULT_LLM_REASONING_EFFORT = "model_default"
SUPPORTED_LLM_REASONING_EFFORTS = {
    DEFAULT_LLM_REASONING_EFFORT,
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
}


def coerce_bool(value: Any, default: bool) -> bool:
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


def coerce_limiter_limit(value: Any, default: int) -> int:
    try:
        return max(1, min(64, int(value)))
    except (TypeError, ValueError):
        return max(1, min(64, int(default)))


def normalize_model_concurrency_overrides(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in raw.items():
        model_name = str(key or "").strip().lower()
        if not model_name:
            continue
        try:
            normalized[model_name] = max(1, min(64, int(value)))
        except (TypeError, ValueError):
            continue
    return normalized


def normalize_openai_api_style(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value == "chat":
        return "chat_completions"
    if value in {"responses", "chat_completions"}:
        return value
    return DEFAULT_LLM_OPENAI_API_STYLE


def normalize_reasoning_effort(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return DEFAULT_LLM_REASONING_EFFORT
    if value in SUPPORTED_LLM_REASONING_EFFORTS:
        return value
    return DEFAULT_LLM_REASONING_EFFORT


def model_supports_reasoning_effort(model: Any) -> bool:
    value = str(model or "").strip().lower()
    if "/" in value:
        _, value = value.split("/", 1)
    return value.startswith("gpt-5") or value.startswith("o1") or value.startswith("o3") or value.startswith("o4")


def default_llm_runtime_config() -> dict[str, Any]:
    return {
        "llm_request_timeout_seconds": int(DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS),
        "llm_retry_count": int(DEFAULT_LLM_RETRY_COUNT),
        "llm_retry_interval_seconds": float(DEFAULT_LLM_RETRY_INTERVAL_SECONDS),
        "llm_prefer_stream": bool(DEFAULT_LLM_PREFER_STREAM),
        "llm_stream_fallback_nonstream": bool(DEFAULT_LLM_STREAM_FALLBACK_NONSTREAM),
        "llm_openai_api_style": str(DEFAULT_LLM_OPENAI_API_STYLE),
        "llm_task_concurrency": int(DEFAULT_LLM_TASK_CONCURRENCY),
        "llm_model_default_concurrency": int(DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY),
        "llm_model_concurrency_overrides": {},
        "llm_reasoning_effort": str(DEFAULT_LLM_REASONING_EFFORT),
    }


def normalize_llm_runtime_config(raw: Any) -> dict[str, Any]:
    payload = default_llm_runtime_config()
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
    payload["llm_prefer_stream"] = coerce_bool(
        current.get("llm_prefer_stream", payload["llm_prefer_stream"]),
        bool(payload["llm_prefer_stream"]),
    )
    payload["llm_stream_fallback_nonstream"] = coerce_bool(
        current.get("llm_stream_fallback_nonstream", payload["llm_stream_fallback_nonstream"]),
        bool(payload["llm_stream_fallback_nonstream"]),
    )
    payload["llm_openai_api_style"] = normalize_openai_api_style(
        current.get("llm_openai_api_style", payload["llm_openai_api_style"])
    )
    payload["llm_task_concurrency"] = coerce_limiter_limit(
        current.get("llm_task_concurrency", payload["llm_task_concurrency"]),
        int(payload["llm_task_concurrency"]),
    )
    payload["llm_model_default_concurrency"] = coerce_limiter_limit(
        current.get("llm_model_default_concurrency", payload["llm_model_default_concurrency"]),
        int(payload["llm_model_default_concurrency"]),
    )
    payload["llm_model_concurrency_overrides"] = normalize_model_concurrency_overrides(
        current.get("llm_model_concurrency_overrides")
    )
    payload["llm_reasoning_effort"] = normalize_reasoning_effort(
        current.get("llm_reasoning_effort", payload["llm_reasoning_effort"])
    )
    return payload

from typing import Any


DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 180


def default_llm_runtime_config() -> dict[str, Any]:
    return {"llm_request_timeout_seconds": DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS}


def normalize_llm_runtime_config(raw: Any) -> dict[str, Any]:
    current = raw if isinstance(raw, dict) else {}
    timeout = int(
        current.get(
            "llm_request_timeout_seconds",
            DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
        )
    )
    if timeout < 5 or timeout > 1800:
        raise ValueError("llm_request_timeout_seconds must be between 5 and 1800")
    return {"llm_request_timeout_seconds": timeout}


def merge_llm_runtime_config(current: Any, body: dict[str, Any]) -> dict[str, Any]:
    return normalize_llm_runtime_config(
        {
            **(current if isinstance(current, dict) else {}),
            **body,
        }
    )

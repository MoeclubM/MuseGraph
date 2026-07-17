"""Unit tests for LLM runtime config normalization."""

from app.services.llm_runtime import merge_llm_runtime_config, normalize_llm_runtime_config


def test_normalize_llm_runtime_config_includes_gateway_defaults():
    cfg = normalize_llm_runtime_config({})
    assert cfg["llm_request_timeout_seconds"] == 180
    assert cfg["llm_prefer_stream"] is True
    assert cfg["llm_task_concurrency"] == 4
    assert cfg["llm_model_default_concurrency"] == 8


def test_merge_llm_runtime_config_preserves_existing_fields():
    merged = merge_llm_runtime_config(
        {"llm_request_timeout_seconds": 90, "llm_retry_count": 1},
        {"llm_retry_count": 3},
    )
    assert merged["llm_request_timeout_seconds"] == 90
    assert merged["llm_retry_count"] == 3
"""Tests for AI service functions."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai import (
    DEFAULT_MODEL,
    OPERATION_COMPONENT_KEYS,
    OPERATION_PROMPTS,
    component_key_for_operation,
    detect_provider,
    resolve_component_model,
)


class TestOperationPrompts:
    """Test operation prompt constants."""

    def test_all_operations_have_prompts(self):
        """Test all operations have defined prompts."""
        operations = ["CREATE", "CONTINUE", "ANALYZE", "REWRITE", "SUMMARIZE"]
        for op in operations:
            assert op in OPERATION_PROMPTS
            assert "{input}" in OPERATION_PROMPTS[op]

    def test_component_keys_exist(self):
        """Test component keys are defined for all operations."""
        operations = ["CREATE", "CONTINUE", "ANALYZE", "REWRITE", "SUMMARIZE"]
        for op in operations:
            assert op in OPERATION_COMPONENT_KEYS


class TestComponentKeyForOperation:
    """Test component_key_for_operation function."""

    def test_valid_operation(self):
        """Test getting component key for valid operation."""
        assert component_key_for_operation("CREATE") == "operation_create"
        assert component_key_for_operation("ANALYZE") == "operation_analyze"

    def test_case_insensitive(self):
        """Test operation type is case insensitive."""
        assert component_key_for_operation("create") == "operation_create"
        assert component_key_for_operation("Create") == "operation_create"

    def test_unknown_operation(self):
        """Test unknown operation returns default."""
        assert component_key_for_operation("UNKNOWN") == "operation_default"
        assert component_key_for_operation("") == "operation_default"
        assert component_key_for_operation(None) == "operation_default"


class TestResolveComponentModel:
    """Test resolve_component_model function."""

    def test_explicit_model_takes_precedence(self):
        """Test explicit model parameter is used first."""
        project = SimpleNamespace(component_models={"operation_create": "gpt-4"})
        result = resolve_component_model(project, "operation_create", "claude-3", "gpt-3.5")
        assert result == "claude-3"

    def test_explicit_model_empty_uses_project_config(self):
        """Test empty explicit model falls back to project config."""
        project = SimpleNamespace(component_models={"operation_create": "gpt-4"})
        result = resolve_component_model(project, "operation_create", "", "gpt-3.5")
        assert result == "gpt-4"

    def test_project_config_operation_default(self):
        """Test fallback to operation_default."""
        project = SimpleNamespace(component_models={"operation_default": "gpt-4o"})
        result = resolve_component_model(project, "operation_unknown", None, "gpt-3.5")
        assert result == "gpt-4o"

    def test_project_config_global_default(self):
        """Test fallback to global default key."""
        project = SimpleNamespace(component_models={"default": "gpt-4o-mini"})
        result = resolve_component_model(project, "any_component", None, "fallback")
        assert result == "gpt-4o-mini"

    def test_fallback_model(self):
        """Test final fallback to fallback_model parameter."""
        project = SimpleNamespace(component_models={})
        result = resolve_component_model(project, "operation_create", None, "fallback-model")
        assert result == "fallback-model"

    def test_none_project(self):
        """Test with None project."""
        result = resolve_component_model(None, "operation_create", None, "fallback")
        assert result == "fallback"

    def test_non_dict_component_models(self):
        """Test with non-dict component_models."""
        project = SimpleNamespace(component_models="not a dict")
        result = resolve_component_model(project, "operation_create", None, "fallback")
        assert result == "fallback"

    def test_whitespace_model(self):
        """Test whitespace-only explicit model is ignored."""
        project = SimpleNamespace(component_models={"operation_create": "gpt-4"})
        result = resolve_component_model(project, "operation_create", "  ", "fallback")
        assert result == "gpt-4"


class TestDetectProvider:
    """Test detect_provider function."""

    def test_openai_models(self):
        """Test detection of OpenAI models."""
        assert detect_provider("gpt-4") == "openai_compatible"
        assert detect_provider("gpt-4o") == "openai_compatible"
        assert detect_provider("gpt-4o-mini") == "openai_compatible"
        assert detect_provider("gpt-3.5-turbo") == "openai_compatible"
        assert detect_provider("o1-preview") == "openai_compatible"
        assert detect_provider("o3-mini") == "openai_compatible"

    def test_anthropic_models(self):
        """Test detection of Anthropic models."""
        assert detect_provider("claude-3-opus") == "anthropic_compatible"
        assert detect_provider("claude-3-haiku") == "anthropic_compatible"
        assert detect_provider("claude-3-5-sonnet") == "anthropic_compatible"

    def test_unknown_model_defaults_to_openai(self):
        """Test unknown model defaults to openai_compatible."""
        assert detect_provider("unknown-model") == "openai_compatible"
        assert detect_provider("") == "openai_compatible"


class TestGetAvailableModels:
    """Test get_available_models function."""

    @pytest.mark.asyncio
    async def test_get_available_models(self, mock_db: AsyncMock):
        """Test getting available models from providers."""
        from app.services.ai import get_available_models

        providers = [
            SimpleNamespace(
                provider="openai_compatible",
                models=["gpt-4o", "gpt-4o-mini"],
                is_active=True,
            ),
            SimpleNamespace(
                provider="anthropic_compatible",
                models=["claude-3-haiku"],
                is_active=True,
            ),
        ]

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = providers
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        models = await get_available_models(mock_db)

        assert len(models) == 3
        model_ids = [m["id"] for m in models]
        assert "gpt-4o" in model_ids
        assert "claude-3-haiku" in model_ids

    @pytest.mark.asyncio
    async def test_get_available_models_empty(self, mock_db: AsyncMock):
        """Test getting models when no providers configured."""
        from app.services.ai import get_available_models

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        models = await get_available_models(mock_db)
        assert models == []


class TestGetPrompt:
    """Test get_prompt function."""

    @pytest.mark.asyncio
    async def test_get_prompt_from_template(self, mock_db: AsyncMock):
        """Test getting prompt from database template."""
        from app.services.ai import get_prompt

        template = SimpleNamespace(
            template="Custom prompt: {input}",
            is_active=True,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=template))

        prompt = await get_prompt("CREATE", "user input", mock_db)

        assert prompt == "Custom prompt: user input"

    @pytest.mark.asyncio
    async def test_get_prompt_default(self, mock_db: AsyncMock):
        """Test getting default prompt when no template."""
        from app.services.ai import get_prompt

        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        prompt = await get_prompt("CREATE", "user input", mock_db)

        assert "user input" in prompt


class TestCalculateCost:
    """Test calculate_cost function."""

    @pytest.mark.asyncio
    async def test_calculate_cost_with_rule(self, mock_db: AsyncMock):
        """Test cost calculation with pricing rule."""
        from app.services.ai import calculate_cost

        rule = SimpleNamespace(
            model="gpt-4o-mini",
            input_price=Decimal("0.15"),
            output_price=Decimal("0.6"),
            token_unit=1_000_000,
            billing_mode="TOKEN",
            is_active=True,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=rule))

        cost = await calculate_cost("gpt-4o-mini", 1000, 500, mock_db)

        # 1M token 口径: 0.15 * 1000/1_000_000 + 0.6 * 500/1_000_000 = 0.00045
        assert cost == Decimal("0.000450")

    @pytest.mark.asyncio
    async def test_calculate_cost_with_request_mode(self, mock_db: AsyncMock):
        from app.services.ai import calculate_cost

        rule = SimpleNamespace(
            model="m2.5",
            input_price=Decimal("0"),
            output_price=Decimal("0"),
            token_unit=1_000_000,
            billing_mode="REQUEST",
            request_price=Decimal("0.123456"),
            is_active=True,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=rule))

        cost = await calculate_cost("m2.5", 99999999, 99999999, mock_db)
        assert cost == Decimal("0.123456")

    @pytest.mark.asyncio
    async def test_calculate_cost_no_rule(self, mock_db: AsyncMock):
        """Test cost calculation returns 0 when no rule."""
        from app.services.ai import calculate_cost

        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        cost = await calculate_cost("unknown-model", 1000, 500, mock_db)
        assert cost == Decimal("0.000000")


class TestCallLLM:
    """Test call_llm function."""

    @pytest.mark.asyncio
    async def test_call_llm_openai(self, mock_db: AsyncMock):
        """Test calling OpenAI-compatible LLM."""
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_response.usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "input_tokens": 100,
            "output_tokens": 50,
        }
        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 2.0,
            "llm_prefer_stream": False,
            "llm_stream_fallback_nonstream": True,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            result = await call_llm("gpt-4o-mini", "Test prompt", mock_db)

            assert result["content"] == "Test response"
            assert result["input_tokens"] == 100
            assert result["output_tokens"] == 50

    @pytest.mark.asyncio
    async def test_call_llm_anthropic(self, mock_db: AsyncMock):
        """Test calling Anthropic-compatible LLM."""
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="anthropic_compatible",
            api_key="test-key",
            base_url=None,
            models=["claude-3-haiku"],
            is_active=True,
        )

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Claude response")]
        mock_response.usage = MagicMock(input_tokens=80, output_tokens=40)

        with patch("anthropic.AsyncAnthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            result = await call_llm("claude-3-haiku", "Test prompt", mock_db)

            assert result["content"] == "Claude response"
            assert result["input_tokens"] == 80

    @pytest.mark.asyncio
    async def test_call_llm_uses_settings_fallback(self, mock_db: AsyncMock):
        """Test call_llm uses settings when no provider config."""
        from app.services.ai import call_llm

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=25)
        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 2.0,
            "llm_prefer_stream": False,
            "llm_stream_fallback_nonstream": True,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai.settings") as mock_settings, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_settings.OPENAI_API_KEY = "settings-key"
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            result = await call_llm("gpt-4o-mini", "Test", mock_db)

            assert result["content"] == "Response"

    @pytest.mark.asyncio
    async def test_call_llm_retries_transient_openai_error(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Recovered response"))]
        mock_response.usage = {
            "prompt_tokens": 60,
            "completion_tokens": 30,
            "input_tokens": 60,
            "output_tokens": 30,
        }
        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
            "llm_stream_fallback_nonstream": True,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[RuntimeError("temporary network issue"), mock_response]
            )
            mock_openai.return_value = mock_client

            result = await call_llm("gpt-4o-mini", "Retry prompt", mock_db)

            assert result["content"] == "Recovered response"
            assert mock_client.chat.completions.create.await_count == 2

    @pytest.mark.asyncio
    async def test_call_llm_does_not_retry_non_retryable_openai_error(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        class _BadRequestError(Exception):
            status_code = 400

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
            "llm_stream_fallback_nonstream": True,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=_BadRequestError("bad request"))
            mock_openai.return_value = mock_client

            with pytest.raises(_BadRequestError):
                await call_llm("gpt-4o-mini", "Bad prompt", mock_db)
            assert mock_client.chat.completions.create.await_count == 1

    @pytest.mark.asyncio
    async def test_call_llm_openai_stream_success(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        async def _stream():
            yield SimpleNamespace(
                usage={"input_tokens": 120, "output_tokens": 0},
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello "))],
            )
            yield SimpleNamespace(
                usage={"input_tokens": 120, "output_tokens": 45},
                choices=[SimpleNamespace(delta=SimpleNamespace(content="stream"))],
            )

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": True,
            "llm_stream_fallback_nonstream": True,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=_stream())
            mock_openai.return_value = mock_client

            result = await call_llm("gpt-4o-mini", "Test stream prompt", mock_db)

            assert result["content"] == "Hello stream"
            assert result["input_tokens"] == 120
            assert result["output_tokens"] == 45
            first_kwargs = mock_client.chat.completions.create.await_args_list[0].kwargs
            assert first_kwargs.get("stream") is True
            assert first_kwargs.get("stream_options") == {"include_usage": True}

    @pytest.mark.asyncio
    async def test_call_llm_openai_stream_failure_fallbacks_to_nonstream(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        nonstream_response = MagicMock()
        nonstream_response.choices = [MagicMock(message=MagicMock(content="Recovered non-stream"))]
        nonstream_response.usage = {
            "prompt_tokens": 90,
            "completion_tokens": 30,
            "input_tokens": 90,
            "output_tokens": 30,
        }

        async def _create_with_stream_fallback(**kwargs):
            if kwargs.get("stream"):
                raise RuntimeError("gateway timeout")
            return nonstream_response

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": True,
            "llm_stream_fallback_nonstream": True,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=_create_with_stream_fallback)
            mock_openai.return_value = mock_client

            result = await call_llm("gpt-4o-mini", "Test stream fallback", mock_db)

            assert result["content"] == "Recovered non-stream"
            assert result["input_tokens"] == 90
            assert result["output_tokens"] == 30
            assert mock_client.chat.completions.create.await_count == 2
            assert mock_client.chat.completions.create.await_args_list[0].kwargs.get("stream") is True
            assert "stream" not in mock_client.chat.completions.create.await_args_list[1].kwargs

    @pytest.mark.asyncio
    async def test_call_llm_openai_stream_failure_without_fallback_raises(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": True,
            "llm_stream_fallback_nonstream": False,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("gateway timeout"))
            mock_openai.return_value = mock_client

            with pytest.raises(RuntimeError, match="gateway timeout"):
                await call_llm("gpt-4o-mini", "No fallback", mock_db)
            assert mock_client.chat.completions.create.await_count == 1

    @pytest.mark.asyncio
    async def test_call_llm_openai_nonstream_when_prefer_stream_disabled(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        nonstream_response = MagicMock()
        nonstream_response.choices = [MagicMock(message=MagicMock(content="Non-stream only"))]
        nonstream_response.usage = {
            "prompt_tokens": 66,
            "completion_tokens": 22,
            "input_tokens": 66,
            "output_tokens": 22,
        }

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
            "llm_stream_fallback_nonstream": True,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=nonstream_response)
            mock_openai.return_value = mock_client

            result = await call_llm("gpt-4o-mini", "No stream preference", mock_db)

            assert result["content"] == "Non-stream only"
            assert result["input_tokens"] == 66
            assert result["output_tokens"] == 22
            assert mock_client.chat.completions.create.await_count == 1
            assert "stream" not in mock_client.chat.completions.create.await_args.kwargs

    @pytest.mark.asyncio
    async def test_call_llm_queues_requests_when_task_concurrency_exceeded(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
            "llm_stream_fallback_nonstream": True,
            "llm_task_concurrency": 1,
            "llm_model_default_concurrency": 32,
            "llm_model_concurrency_overrides": {},
        }

        observed = {"inflight": 0, "max_inflight": 0}

        async def _slow_nonstream(**kwargs):
            observed["inflight"] += 1
            observed["max_inflight"] = max(observed["max_inflight"], observed["inflight"])
            await asyncio.sleep(0.03)
            observed["inflight"] -= 1
            response = MagicMock()
            response.choices = [MagicMock(message=MagicMock(content="queued"))]
            response.usage = {"input_tokens": 10, "output_tokens": 5}
            return response

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=_slow_nonstream)
            mock_openai.return_value = mock_client

            await asyncio.gather(
                call_llm("gpt-4o-mini", "Prompt A", mock_db, billing_operation_id="task-queue-1"),
                call_llm("gpt-4o-mini", "Prompt B", mock_db, billing_operation_id="task-queue-1"),
                call_llm("gpt-4o-mini", "Prompt C", mock_db, billing_operation_id="task-queue-1"),
            )

            assert observed["max_inflight"] == 1

    @pytest.mark.asyncio
    async def test_call_llm_respects_per_model_concurrency_overrides(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o-mini"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
            "llm_stream_fallback_nonstream": True,
            "llm_task_concurrency": 8,
            "llm_model_default_concurrency": 32,
            "llm_model_concurrency_overrides": {"gpt-4o-mini": 1},
        }

        observed = {"inflight": 0, "max_inflight": 0}

        async def _slow_nonstream(**kwargs):
            observed["inflight"] += 1
            observed["max_inflight"] = max(observed["max_inflight"], observed["inflight"])
            await asyncio.sleep(0.03)
            observed["inflight"] -= 1
            response = MagicMock()
            response.choices = [MagicMock(message=MagicMock(content="model-limited"))]
            response.usage = {"input_tokens": 10, "output_tokens": 5}
            return response

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=_slow_nonstream)
            mock_openai.return_value = mock_client

            await asyncio.gather(
                call_llm("gpt-4o-mini", "Prompt A", mock_db, billing_operation_id="task-model-a"),
                call_llm("gpt-4o-mini", "Prompt B", mock_db, billing_operation_id="task-model-b"),
                call_llm("gpt-4o-mini", "Prompt C", mock_db, billing_operation_id="task-model-c"),
            )

            assert observed["max_inflight"] == 1


class TestRunOperation:
    """Test run_operation function."""

    @pytest.mark.asyncio
    async def test_run_operation_success(self, mock_db: AsyncMock):
        """Test successful operation execution."""
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-1",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
        )
        project = SimpleNamespace(
            id="proj-1",
            content="Project content",
        )
        user = SimpleNamespace(
            id="user-1",
            balance=Decimal("100.00"),
        )

        mock_db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=operation))

        with patch("app.services.ai.get_prompt") as mock_get_prompt, \
             patch("app.services.ai.call_llm") as mock_call_llm, \
             patch("app.services.ai.calculate_cost") as mock_calc_cost:
            mock_get_prompt.return_value = "Test prompt"
            mock_call_llm.return_value = {
                "content": "Generated content",
                "input_tokens": 100,
                "output_tokens": 50,
            }
            mock_calc_cost.return_value = Decimal("0.05")

            result = await run_operation(
                operation_id="op-1",
                project=project,
                user=user,
                op_type="CREATE",
                input_text="Input text",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result.status == "COMPLETED"
            assert result.output == "Generated content"
            assert result.cost == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_run_operation_with_prediction_enhancement(self, mock_db: AsyncMock):
        """Test operation with prediction enhancement."""
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-1",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
        )
        project = SimpleNamespace(id="proj-1", content="Content")
        user = SimpleNamespace(id="user-1", balance=Decimal("100"))

        mock_db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=operation))

        with patch("app.services.ai.get_prompt") as mock_get_prompt, \
             patch("app.services.ai.call_llm") as mock_call_llm, \
             patch("app.services.ai.calculate_cost") as mock_calc_cost, \
             patch("app.services.prediction.get_enhanced_prompt") as mock_enhance:
            mock_get_prompt.return_value = "Base prompt"
            mock_enhance.return_value = "Enhanced prompt"
            mock_call_llm.return_value = {"content": "Result", "input_tokens": 50, "output_tokens": 25}
            mock_calc_cost.return_value = Decimal("0.01")

            await run_operation(
                operation_id="op-1",
                project=project,
                user=user,
                op_type="CREATE",
                input_text="Input",
                model="gpt-4o-mini",
                db=mock_db,
            )

            mock_enhance.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_operation_handles_error(self, mock_db: AsyncMock):
        """Test operation handles errors gracefully."""
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-1",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
        )
        project = SimpleNamespace(id="proj-1", content="Content")
        user = SimpleNamespace(id="user-1", balance=Decimal("100"))

        mock_db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=operation))

        with patch("app.services.ai.get_prompt") as mock_get_prompt, \
             patch("app.services.ai.call_llm") as mock_call_llm:
            mock_get_prompt.return_value = "Prompt"
            mock_call_llm.side_effect = Exception("LLM error")

            result = await run_operation(
                operation_id="op-1",
                project=project,
                user=user,
                op_type="CREATE",
                input_text="Input",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result.status == "FAILED"
            assert "LLM error" in result.error

    @pytest.mark.asyncio
    async def test_run_operation_insufficient_balance(self, mock_db: AsyncMock):
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-3",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
        )
        project = SimpleNamespace(id="proj-1", content="Content")
        user = SimpleNamespace(id="user-1", balance=Decimal("0.010000"))

        mock_db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=operation))

        with patch("app.services.ai.get_prompt") as mock_get_prompt, \
             patch("app.services.ai.call_llm") as mock_call_llm, \
             patch("app.services.ai.calculate_cost") as mock_calc_cost:
            mock_get_prompt.return_value = "Prompt"
            mock_call_llm.return_value = {"content": "OK", "input_tokens": 10, "output_tokens": 10}
            mock_calc_cost.return_value = Decimal("0.020000")

            result = await run_operation(
                operation_id="op-3",
                project=project,
                user=user,
                op_type="CREATE",
                input_text="Input",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result.status == "FAILED"
            assert "Insufficient balance" in (result.error or "")


class TestRunOperationAsync:
    """Test run_operation_async function."""

    @pytest.mark.asyncio
    async def test_run_operation_async_basic(self, mock_db: AsyncMock):
        """Test async operation execution."""
        # This test is simplified to avoid complex mocking of async context manager
        # The core functionality is tested in TestRunOperation
        pass


# ---------------------------------------------------------------------------
# Additional tests for missing coverage
# ---------------------------------------------------------------------------


class TestCallLLMFallback:
    """Test call_llm when no config has the model, falls back to provider detection (lines 116-118)."""

    @pytest.mark.asyncio
    async def test_fallback_to_provider_detection_openai(self, mock_db: AsyncMock):
        """No config lists the model, but a config matches the detected provider."""
        from app.services.ai import call_llm

        # Config does NOT list "gpt-4-turbo" in its models, but provider matches
        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="fallback-key",
            base_url=None,
            models=["gpt-4o"],  # does NOT contain gpt-4-turbo
            is_active=True,
        )

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Fallback response"))]
        mock_response.usage = {
            "prompt_tokens": 60,
            "completion_tokens": 30,
            "input_tokens": 60,
            "output_tokens": 30,
        }
        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 2.0,
            "llm_prefer_stream": False,
            "llm_stream_fallback_nonstream": True,
        }

        with patch("openai.AsyncOpenAI") as mock_openai, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            result = await call_llm("gpt-4-turbo", "Test prompt", mock_db)

        assert result["content"] == "Fallback response"
        assert result["input_tokens"] == 60

    @pytest.mark.asyncio
    async def test_fallback_to_provider_detection_anthropic(self, mock_db: AsyncMock):
        """Fallback path for anthropic model not listed in any config."""
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="anthropic_compatible",
            api_key="ant-key",
            base_url=None,
            models=["claude-3-opus"],  # does NOT contain claude-3-5-sonnet
            is_active=True,
        )

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Anthropic fallback")]
        mock_response.usage = MagicMock(input_tokens=40, output_tokens=20)

        with patch("anthropic.AsyncAnthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            result = await call_llm("claude-3-5-sonnet", "Test", mock_db)

        assert result["content"] == "Anthropic fallback"
        assert result["input_tokens"] == 40


class TestCallLLMUnsupportedProvider:
    """Test ValueError for unsupported provider (line 154)."""

    @pytest.mark.asyncio
    async def test_unsupported_provider_raises(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="some_unknown_provider",
            api_key="key",
            base_url=None,
            models=["custom-model"],
            is_active=True,
        )

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        with pytest.raises(ValueError, match="Unsupported provider"):
            await call_llm("custom-model", "prompt", mock_db)


class TestRunOperationFull:
    """Test run_operation success with all steps (lines 170-240)."""

    @pytest.mark.asyncio
    async def test_full_flow_with_cost_and_usage(self, mock_db: AsyncMock):
        """Verify balance deduction and usage record creation."""
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-1",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
        )
        project = SimpleNamespace(id="proj-1", content="Project text")
        user = SimpleNamespace(id="user-1", balance=Decimal("50.00"))

        mock_db.execute.return_value = MagicMock(
            scalar_one=MagicMock(return_value=operation)
        )

        with patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value="Full prompt"), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.ai.calculate_cost", new_callable=AsyncMock) as mock_cost, \
             patch("app.services.prediction.get_enhanced_prompt", new_callable=AsyncMock, return_value="Full prompt"):
            mock_llm.return_value = {"content": "Output text", "input_tokens": 200, "output_tokens": 100}
            mock_cost.return_value = Decimal("0.10")

            result = await run_operation("op-1", project, user, "CREATE", "Input", "gpt-4o-mini", mock_db)

        assert result.status == "COMPLETED"
        assert result.output == "Output text"
        assert result.input_tokens == 200
        assert result.output_tokens == 100
        assert result.cost == Decimal("0.10")
        assert user.balance == Decimal("49.90")
        # Usage record was added
        mock_db.add.assert_called()


class TestRunOperationPredictionException:
    """Test run_operation when prediction enhancement raises (lines 203-204)."""

    @pytest.mark.asyncio
    async def test_prediction_exception_caught(self, mock_db: AsyncMock):
        """Enhancement failure should be silently caught, operation still succeeds."""
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-2",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
        )
        project = SimpleNamespace(id="proj-1", content="text")
        user = SimpleNamespace(id="user-1", balance=Decimal("10.00"))

        mock_db.execute.return_value = MagicMock(
            scalar_one=MagicMock(return_value=operation)
        )

        with patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value="prompt"), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.ai.calculate_cost", new_callable=AsyncMock, return_value=Decimal("0.01")), \
             patch("app.services.prediction.get_enhanced_prompt", new_callable=AsyncMock, side_effect=RuntimeError("prediction down")):
            mock_llm.return_value = {"content": "OK", "input_tokens": 10, "output_tokens": 5}

            result = await run_operation("op-2", project, user, "CONTINUE", "inp", "gpt-4o-mini", mock_db)

        assert result.status == "COMPLETED"
        assert result.output == "OK"


class TestRunOperationAsyncFull:
    """Test run_operation_async entire function (lines 265-376)."""

    @pytest.mark.asyncio
    async def test_async_success_flow(self):
        """Full async flow: fetch entities, call LLM, publish progress, commit."""
        from app.services.ai import run_operation_async

        operation = SimpleNamespace(
            id="op-async-1",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
        )
        project = SimpleNamespace(id="proj-1", content="text")
        user = SimpleNamespace(id="user-1", balance=Decimal("20.00"))

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        # Three sequential execute calls: operation, project, user
        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one=MagicMock(return_value=operation)),
            MagicMock(scalar_one=MagicMock(return_value=project)),
            MagicMock(scalar_one=MagicMock(return_value=user)),
        ])

        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch("app.database.async_session") as mock_session_ctx, \
             patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value="prompt"), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.ai.calculate_cost", new_callable=AsyncMock, return_value=Decimal("0.05")), \
             patch("app.services.ai.redis_client", mock_redis), \
             patch("app.services.prediction.get_enhanced_prompt", new_callable=AsyncMock, return_value="prompt"):
            mock_llm.return_value = {"content": "Async output", "input_tokens": 80, "output_tokens": 40}

            # async context manager
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_operation_async("op-async-1", "proj-1", "user-1", "CREATE", "input", "gpt-4o-mini")

        assert operation.status == "COMPLETED"
        assert operation.output == "Async output"
        assert operation.progress == 100
        assert user.balance == Decimal("19.95")
        mock_session.commit.assert_called()
        # Redis publish called multiple times for progress updates
        assert mock_redis.publish.call_count >= 3

    @pytest.mark.asyncio
    async def test_async_failure_flow(self):
        """Test run_operation_async when call_llm raises, publishes FAILED."""
        from app.services.ai import run_operation_async

        operation = SimpleNamespace(
            id="op-fail",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
        )
        project = SimpleNamespace(id="proj-1", content="text")
        user = SimpleNamespace(id="user-1", balance=Decimal("10.00"))

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one=MagicMock(return_value=operation)),
            MagicMock(scalar_one=MagicMock(return_value=project)),
            MagicMock(scalar_one=MagicMock(return_value=user)),
        ])

        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch("app.database.async_session") as mock_ctx, \
             patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value="p"), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")), \
             patch("app.services.ai.redis_client", mock_redis), \
             patch("app.services.prediction.get_enhanced_prompt", new_callable=AsyncMock, return_value="p"):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_operation_async("op-fail", "proj-1", "user-1", "CREATE", "input", "gpt-4o-mini")

        assert operation.status == "FAILED"
        assert "LLM down" in operation.error
        mock_session.commit.assert_called()

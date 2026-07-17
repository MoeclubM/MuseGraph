"""Tests for AI service functions."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ConfigDict, BaseModel

from app.services.ai import (
    OPERATION_COMPONENT_KEYS,
    OPERATION_PROMPTS,
    SUPPORTED_TEXT_OPERATION_TYPES,
    component_key_for_operation,
    resolve_explicit_component_model,
)


def _mock_openai_response(content: str, input_tokens: int, output_tokens: int):
    response = MagicMock()
    response.output_text = content
    response.usage = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    return response


def _mock_openai_chat_response(content: str, input_tokens: int, output_tokens: int):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    response.usage = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    return response


class TestOperationPrompts:
    """Test operation prompt constants."""

    def test_all_operations_have_prompts(self):
        """Test all operations have defined prompts."""
        for op in SUPPORTED_TEXT_OPERATION_TYPES:
            assert op in OPERATION_PROMPTS
            assert "{input}" in OPERATION_PROMPTS[op]

    def test_component_keys_exist(self):
        """Test component keys are defined for all operations."""
        for op in SUPPORTED_TEXT_OPERATION_TYPES:
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
        """Test unknown operation fails explicitly."""
        with pytest.raises(ValueError, match="Unsupported operation type"):
            component_key_for_operation("UNKNOWN")
        with pytest.raises(ValueError, match="Unsupported operation type"):
            component_key_for_operation("")
        with pytest.raises(ValueError, match="Unsupported operation type"):
            component_key_for_operation(None)


class TestResolveExplicitComponentModel:
    """Test resolve_explicit_component_model function."""

    def test_explicit_model_takes_precedence(self):
        """Test explicit model parameter is used first."""
        project = SimpleNamespace(component_models={"operation_create": "gpt-4"})
        result = resolve_explicit_component_model(project, "operation_create", "claude-3")
        assert result == "claude-3"

    def test_explicit_model_empty_uses_project_config(self):
        """Test empty explicit model uses project component config."""
        project = SimpleNamespace(component_models={"operation_create": "gpt-4"})
        result = resolve_explicit_component_model(project, "operation_create", "")
        assert result == "gpt-4"

    def test_project_config_global_default_is_not_used(self):
        """Test global default is not an implicit component model."""
        project = SimpleNamespace(component_models={"default": "gpt-4o-mini"})
        result = resolve_explicit_component_model(project, "any_component", None)
        assert result == ""

    def test_missing_model_returns_empty(self):
        """Test missing component model returns empty for caller-side explicit error."""
        project = SimpleNamespace(component_models={})
        result = resolve_explicit_component_model(project, "operation_create", None)
        assert result == ""

    def test_none_project(self):
        """Test with None project."""
        result = resolve_explicit_component_model(None, "operation_create", None)
        assert result == ""

    def test_non_dict_component_models(self):
        """Test with non-dict component_models."""
        project = SimpleNamespace(component_models="not a dict")
        result = resolve_explicit_component_model(project, "operation_create", None)
        assert result == ""

    def test_whitespace_model(self):
        """Test whitespace-only explicit model is ignored."""
        project = SimpleNamespace(component_models={"operation_create": "gpt-4"})
        result = resolve_explicit_component_model(project, "operation_create", "  ")
        assert result == "gpt-4"


class TestGetAvailableModels:
    """Test get_available_models function."""

    @pytest.mark.asyncio
    async def test_get_available_models(self, mock_db: AsyncMock):
        """Test getting available models from providers."""
        from app.services.ai import get_available_models

        providers = [
            SimpleNamespace(
                name="Primary Provider",
                provider="openai_compatible",
                models=["gpt-4o", "gpt-4o-mini"],
                is_active=True,
            ),
            SimpleNamespace(
                name="Anthropic Provider",
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
        provider_by_model = {m["id"]: m["provider"] for m in models}
        assert provider_by_model["gpt-4o"] == "Primary Provider"
        assert provider_by_model["claude-3-haiku"] == "Anthropic Provider"

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

    @pytest.mark.asyncio
    async def test_get_available_embedding_and_reranker_models(self, mock_db: AsyncMock):
        from app.services.ai import get_available_embedding_models, get_available_reranker_models

        providers = [
            SimpleNamespace(
                name="Telecom Qwen",
                provider="openai_compatible",
                models={
                    "models": ["chat-model"],
                    "embedding_models": ["Qwen3-Embedding-0.6B"],
                    "reranker_models": ["Qwen3-Reranker-0.6B"],
                },
                is_active=True,
            ),
        ]
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = providers
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        embedding_models = await get_available_embedding_models(mock_db)
        reranker_models = await get_available_reranker_models(mock_db)

        assert embedding_models == [
            {
                "id": "Qwen3-Embedding-0.6B",
                "provider": "Telecom Qwen",
                "name": "Qwen3-Embedding-0.6B",
            }
        ]
        assert reranker_models == [
            {
                "id": "Qwen3-Reranker-0.6B",
                "provider": "Telecom Qwen",
                "name": "Qwen3-Reranker-0.6B",
            }
        ]


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

    @pytest.mark.asyncio
    async def test_get_prompt_project_override_takes_precedence(self, mock_db: AsyncMock):
        from app.services.ai import get_prompt

        project = SimpleNamespace(operation_prompts={"CREATE": "Project prompt: {input}"})

        prompt = await get_prompt("CREATE", "user input", mock_db, project=project)

        assert prompt == "Project prompt: user input"
        mock_db.execute.assert_not_awaited()


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

        mock_response = _mock_openai_response("Test response", 100, 50)
        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 2.0,
            "llm_prefer_stream": False,
        }

        with patch("app.services.ai.litellm.aresponses", new=AsyncMock(return_value=mock_response)), \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            result = await call_llm("gpt-4o-mini", "Test prompt", mock_db)

            assert result["content"] == "Test response"
            assert result["input_tokens"] == 100
            assert result["output_tokens"] == 50

    @pytest.mark.asyncio
    async def test_call_llm_openai_responses_uses_json_schema_when_provided(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        class StructuredResponse(BaseModel):
            model_config = ConfigDict(extra="forbid")

            answer: str

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
        }

        with patch(
            "app.services.ai.litellm.aresponses",
            new=AsyncMock(return_value=_mock_openai_response('{"answer":"ok"}', 8, 4)),
        ) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm(
                "gpt-4o-mini",
                "Test prompt",
                mock_db,
                response_schema=StructuredResponse,
            )

            request_kwargs = mock_aresponses.await_args.kwargs
            assert request_kwargs["text"]["format"]["type"] == "json_schema"
            assert request_kwargs["text"]["format"]["name"] == "StructuredResponse"
            assert request_kwargs["text"]["format"]["strict"] is True
            assert request_kwargs["text"]["format"]["schema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_call_llm_openai_responses_passes_reasoning_effort_for_gpt5(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-5.4"],
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
            "llm_reasoning_effort": "minimal",
        }

        with patch(
            "app.services.ai.litellm.aresponses",
            new=AsyncMock(return_value=_mock_openai_response("ok", 8, 4)),
        ) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm("gpt-5.4", "Test prompt", mock_db)

            request_kwargs = mock_aresponses.await_args.kwargs
            assert request_kwargs["reasoning"] == {"effort": "minimal"}

    @pytest.mark.asyncio
    async def test_call_llm_openai_responses_passes_reasoning_effort_for_gpt54_compact(
        self,
        mock_db: AsyncMock,
    ):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-5.4-openai-compact"],
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
            "llm_reasoning_effort": "none",
        }

        with patch(
            "app.services.ai.litellm.aresponses",
            new=AsyncMock(return_value=_mock_openai_response("ok", 8, 4)),
        ) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm("gpt-5.4-openai-compact", "Test prompt", mock_db)

            request_kwargs = mock_aresponses.await_args.kwargs
            assert request_kwargs["reasoning"] == {"effort": "none"}

    @pytest.mark.asyncio
    async def test_call_llm_openai_chat_completions_uses_json_schema_when_provided(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        class StructuredResponse(BaseModel):
            model_config = ConfigDict(extra="forbid")

            answer: str

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
            "llm_openai_api_style": "chat_completions",
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(return_value=_mock_openai_chat_response('{"answer":"ok"}', 12, 5)),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm(
                "gpt-4o-mini",
                "Test prompt",
                mock_db,
                response_schema=StructuredResponse,
            )

            request_kwargs = mock_acompletion.await_args.kwargs
            assert request_kwargs["response_format"]["type"] == "json_schema"
            assert request_kwargs["response_format"]["json_schema"]["name"] == "StructuredResponse"
            assert request_kwargs["response_format"]["json_schema"]["strict"] is True
            assert request_kwargs["response_format"]["json_schema"]["schema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_call_llm_deepseek_chat_completions_uses_json_object_with_example(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        class StructuredResponse(BaseModel):
            model_config = ConfigDict(extra="forbid")

            answer: str

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["deepseek-v4-pro"],
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
            "llm_openai_api_style": "chat_completions",
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(return_value=_mock_openai_chat_response('{"answer":"ok"}', 12, 5)),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm(
                "deepseek-v4-pro",
                "Test prompt",
                mock_db,
                response_schema=StructuredResponse,
            )

            request_kwargs = mock_acompletion.await_args.kwargs
            assert request_kwargs["response_format"] == {"type": "json_object"}
            assert request_kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
            message = request_kwargs["messages"][0]["content"]
            assert "Return valid json only" in message
            assert "EXAMPLE JSON OUTPUT" in message
            assert '"answer"' in message

    @pytest.mark.asyncio
    async def test_call_llm_chat_completions_dict_schema_can_request_json_object(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-5.5"],
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
            "llm_openai_api_style": "chat_completions",
        }
        action_schema = {
            "x_musegraph_response_format": "json_object",
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["tool_call", "finish"]},
                "tool": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(return_value=_mock_openai_chat_response('{"action":"finish"}', 12, 5)),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm(
                "gpt-5.5",
                "Test prompt",
                mock_db,
                response_schema=action_schema,
                response_schema_name="PiToolAction",
            )

            request_kwargs = mock_acompletion.await_args.kwargs
            assert request_kwargs["response_format"] == {"type": "json_object"}
            message = request_kwargs["messages"][0]["content"]
            assert "EXAMPLE JSON OUTPUT" in message
            assert '"action": "tool_call"' in message
            assert "x_musegraph_response_format" not in message

    @pytest.mark.asyncio
    async def test_call_llm_ark_chat_completions_uses_prompt_only_json_schema(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["ark-code-latest"],
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
            "llm_openai_api_style": "chat_completions",
        }
        action_schema = {
            "x_musegraph_response_format": "json_object",
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["tool_call", "finish"]},
                "tool": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(return_value=_mock_openai_chat_response('{"action":"finish"}', 12, 5)),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm(
                "ark-code-latest",
                "Test prompt",
                mock_db,
                response_schema=action_schema,
                response_schema_name="PiToolAction",
            )

            request_kwargs = mock_acompletion.await_args.kwargs
            assert "response_format" not in request_kwargs
            message = request_kwargs["messages"][0]["content"]
            assert "Return valid json only" in message
            assert "EXAMPLE JSON OUTPUT" in message
            assert "x_musegraph_response_format" not in message

    def test_ark_is_not_structured_json_model(self):
        from app.services.ai import model_supports_structured_json, require_structured_json_model

        assert model_supports_structured_json("mimo") is True
        assert model_supports_structured_json("ark-code-latest") is False
        with pytest.raises(RuntimeError, match="only supported for Agent tool-calling/write flows"):
            require_structured_json_model("ark-code-latest", "Project graph extraction")

    @pytest.mark.asyncio
    async def test_call_llm_openai_chat_completions_passes_reasoning_effort_for_gpt5(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-5.4"],
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
            "llm_openai_api_style": "chat_completions",
            "llm_reasoning_effort": "high",
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(return_value=_mock_openai_chat_response("ok", 12, 5)),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm("gpt-5.4", "Test prompt", mock_db)

            request_kwargs = mock_acompletion.await_args.kwargs
            assert request_kwargs["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_call_llm_deepseek_chat_completions_enables_thinking(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["deepseek-v4-pro"],
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
            "llm_openai_api_style": "chat_completions",
            "llm_reasoning_effort": "low",
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(return_value=_mock_openai_chat_response("ok", 12, 5)),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            await call_llm("deepseek-v4-pro", "Test prompt", mock_db)

            request_kwargs = mock_acompletion.await_args.kwargs
            assert request_kwargs["reasoning_effort"] == "low"
            assert request_kwargs["extra_body"] == {"thinking": {"type": "enabled"}}

    @pytest.mark.asyncio
    async def test_call_llm_openai_chat_completions_empty_content_raises(self, mock_db: AsyncMock):
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
            "llm_openai_api_style": "chat_completions",
        }

        response = _mock_openai_chat_response("", 16, 0)
        response.model = "crow-9b-heretic-4.6"

        with patch("app.services.ai.litellm.acompletion", new=AsyncMock(return_value=response)), \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            with pytest.raises(RuntimeError, match='provider_model=\"crow-9b-heretic-4.6\"'):
                await call_llm("gpt-4o-mini", "Empty prompt", mock_db)

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

        mock_response = _mock_openai_chat_response("Claude response", 80, 40)

        with patch("app.services.ai.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await call_llm("claude-3-haiku", "Test prompt", mock_db)

            assert result["content"] == "Claude response"
            assert result["input_tokens"] == 80

    @pytest.mark.asyncio
    async def test_call_llm_anthropic_structured_schema_uses_json_prompt(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        class StructuredResponse(BaseModel):
            model_config = ConfigDict(extra="forbid")

            answer: str

        config = SimpleNamespace(
            provider="anthropic_compatible",
            api_key="test-key",
            base_url="https://api.deepseek.com/anthropic",
            models=["deepseek-v4-pro"],
            is_active=True,
        )

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        mock_response = _mock_openai_chat_response('{"answer":"ok"}', 80, 40)

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
            "llm_reasoning_effort": "high",
        }

        with patch("app.services.ai.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            result = await call_llm(
                "deepseek-v4-pro",
                "Test prompt",
                mock_db,
                response_schema=StructuredResponse,
            )

            request_kwargs = mock_acompletion.await_args.kwargs
            assert result["content"] == '{"answer":"ok"}'
            assert request_kwargs["extra_body"] == {
                "thinking": {"type": "enabled"},
                "output_config": {"effort": "high"},
            }
            message = request_kwargs["messages"][0]["content"]
            assert "Return valid json only" in message
            assert "EXAMPLE JSON OUTPUT" in message
            assert '"answer"' in message

    @pytest.mark.asyncio
    async def test_call_llm_requires_admin_provider_config(self, mock_db: AsyncMock):
        """Test call_llm rejects requests when no provider is configured in admin."""
        from app.services.ai import call_llm

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 2.0,
            "llm_prefer_stream": False,
        }

        with patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            with pytest.raises(ValueError, match="No active provider has registered model"):
                await call_llm("gpt-4o-mini", "Test", mock_db)

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

        mock_response = _mock_openai_response("Recovered response", 60, 30)
        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
        }

        with patch(
            "app.services.ai.litellm.aresponses",
            new=AsyncMock(side_effect=[RuntimeError("temporary network issue"), mock_response]),
        ) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            result = await call_llm("gpt-4o-mini", "Retry prompt", mock_db)

            assert result["content"] == "Recovered response"
            assert mock_aresponses.await_count == 2

    @pytest.mark.asyncio
    async def test_call_llm_retries_non_200_openai_error(self, mock_db: AsyncMock):
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
            "llm_retry_count": 1,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
        }

        with patch("app.services.ai.litellm.aresponses", new=AsyncMock(side_effect=_BadRequestError("bad request"))) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            with pytest.raises(RuntimeError, match='LLM provider request failed.*gpt-4o-mini.*bad request') as exc_info:
                await call_llm("gpt-4o-mini", "Bad prompt", mock_db)
            assert getattr(exc_info.value, "status_code", None) == 400
            assert mock_aresponses.await_count == 2

    @pytest.mark.asyncio
    async def test_call_llm_sanitizes_html_error_after_retries(self, mock_db: AsyncMock):
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

        class _GatewayHtmlError(Exception):
            status_code = 502

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 1,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
        }

        with patch(
            "app.services.ai.litellm.aresponses",
            new=AsyncMock(
                side_effect=_GatewayHtmlError("<!DOCTYPE html><html><body><h1>502 Bad Gateway</h1></body></html>")
            ),
        ) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            with pytest.raises(RuntimeError) as exc_info:
                await call_llm("gpt-4o-mini", "Bad gateway prompt", mock_db)

            assert "HTTP 502" in str(exc_info.value)
            assert "<html" not in str(exc_info.value).lower()
            assert mock_aresponses.await_count == 2

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
                type="response.output_text.delta",
                delta="Hello ",
            )
            yield SimpleNamespace(
                type="response.output_text.delta",
                delta="stream",
            )
            yield SimpleNamespace(
                type="response.completed",
                response=_mock_openai_response("Hello stream", 120, 45),
            )

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": True,
        }

        with patch("app.services.ai.litellm.aresponses", new=AsyncMock(return_value=_stream())) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            result = await call_llm("gpt-4o-mini", "Test stream prompt", mock_db)

            assert result["content"] == "Hello stream"
            assert result["input_tokens"] == 120
            assert result["output_tokens"] == 45
            first_kwargs = mock_aresponses.await_args_list[0].kwargs
            assert first_kwargs.get("stream") is True

    @pytest.mark.asyncio
    async def test_call_llm_openai_stream_failure_raises(self, mock_db: AsyncMock):
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
        }

        with patch("app.services.ai.litellm.aresponses", new=AsyncMock(side_effect=RuntimeError("gateway timeout"))) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            with pytest.raises(RuntimeError, match="gateway timeout"):
                await call_llm("gpt-4o-mini", "No fallback", mock_db)
            assert mock_aresponses.await_count == 1

    @pytest.mark.asyncio
    async def test_call_llm_openai_chat_completions_nonstream_when_configured(self, mock_db: AsyncMock):
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
            "llm_openai_api_style": "chat_completions",
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(return_value=_mock_openai_chat_response("Chat completion", 42, 21)),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            result = await call_llm("gpt-4o-mini", "Chat prompt", mock_db)

            assert result["content"] == "Chat completion"
            assert result["input_tokens"] == 42
            assert result["output_tokens"] == 21
            assert mock_acompletion.await_count == 1

    @pytest.mark.asyncio
    async def test_call_llm_openai_chat_completions_stream_success(self, mock_db: AsyncMock):
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
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello "), finish_reason=None)],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="chat"), finish_reason=None)],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")],
                usage={"prompt_tokens": 55, "completion_tokens": 23},
            )

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": True,
            "llm_openai_api_style": "chat_completions",
        }

        with patch("app.services.ai.litellm.acompletion", new=AsyncMock(return_value=_stream())) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            result = await call_llm("gpt-4o-mini", "Chat stream prompt", mock_db)

            assert result["content"] == "Hello chat"
            assert result["input_tokens"] == 55
            assert result["output_tokens"] == 23
            first_kwargs = mock_acompletion.await_args_list[0].kwargs
            assert first_kwargs.get("stream") is True
            assert first_kwargs.get("stream_options") == {"include_usage": True}

    @pytest.mark.asyncio
    async def test_call_llm_chat_completions_stream_retries_empty_content(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["deepseek-v4-flash"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        async def _empty_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")],
                usage={"prompt_tokens": 20, "completion_tokens": 0},
            )

        async def _success_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content='{"ok":true}'), finish_reason=None)],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")],
                usage={"prompt_tokens": 30, "completion_tokens": 8},
            )

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 1,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": True,
            "llm_openai_api_style": "chat_completions",
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(side_effect=[_empty_stream(), _success_stream()]),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            result = await call_llm("deepseek-v4-flash", "Chat stream prompt", mock_db)

            assert result["content"] == '{"ok":true}'
            assert result["input_tokens"] == 30
            assert result["output_tokens"] == 8
            assert mock_acompletion.await_count == 2
            first_kwargs = mock_acompletion.await_args_list[0].kwargs
            assert first_kwargs["extra_body"] == {"thinking": {"type": "enabled"}}

    @pytest.mark.asyncio
    async def test_call_llm_chat_completions_stream_empty_after_retries_raises(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["deepseek-v4-flash"],
            is_active=True,
        )
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        async def _empty_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")],
                usage={"prompt_tokens": 20, "completion_tokens": 0},
            )

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 1,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": True,
            "llm_openai_api_style": "chat_completions",
        }

        with patch(
            "app.services.ai.litellm.acompletion",
            new=AsyncMock(side_effect=[_empty_stream(), _empty_stream()]),
        ) as mock_acompletion, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            with pytest.raises(RuntimeError, match='LLM returned empty content.*deepseek-v4-flash'):
                await call_llm("deepseek-v4-flash", "Chat stream prompt", mock_db)
            assert mock_acompletion.await_count == 2

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

        nonstream_response = _mock_openai_response("Non-stream only", 66, 22)

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 0,
            "llm_retry_interval_seconds": 0.0,
            "llm_prefer_stream": False,
        }

        with patch("app.services.ai.litellm.aresponses", new=AsyncMock(return_value=nonstream_response)) as mock_aresponses, \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            result = await call_llm("gpt-4o-mini", "No stream preference", mock_db)

            assert result["content"] == "Non-stream only"
            assert result["input_tokens"] == 66
            assert result["output_tokens"] == 22
            assert mock_aresponses.await_count == 1
            assert "stream" not in mock_aresponses.await_args.kwargs

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
            return _mock_openai_response("queued", 10, 5)

        with patch("app.services.ai.litellm.aresponses", new=AsyncMock(side_effect=_slow_nonstream)), \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
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
            return _mock_openai_response("model-limited", 10, 5)

        with patch("app.services.ai.litellm.aresponses", new=AsyncMock(side_effect=_slow_nonstream)), \
             patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
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
            chapters=[],
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
                "cost": Decimal("0.05"),
                "usage_recorded": True,
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
    async def test_run_operation_with_creative_memory_enhancement(self, mock_db: AsyncMock):
        """Test operation with creative memory enhancement."""
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
        project = SimpleNamespace(id="proj-1", content="Content", memory_id="memory-1", chapters=[])
        user = SimpleNamespace(id="user-1", balance=Decimal("100"))

        mock_db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=operation))

        with patch("app.services.ai.get_prompt") as mock_get_prompt, \
             patch("app.services.ai.call_llm") as mock_call_llm, \
             patch("app.services.ai.calculate_cost") as mock_calc_cost, \
             patch("app.services.creative_memory.build_creative_memory_pack") as mock_enhance:
            mock_get_prompt.return_value = "Base prompt"
            mock_enhance.return_value = {}
            mock_call_llm.return_value = {
                "content": "Result",
                "input_tokens": 50,
                "output_tokens": 25,
                "cost": Decimal("0.01"),
                "usage_recorded": True,
            }
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
        project = SimpleNamespace(id="proj-1", content="Content", chapters=[])
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
        project = SimpleNamespace(id="proj-1", content="Content", chapters=[])
        user = SimpleNamespace(id="user-1", balance=Decimal("0.010000"))

        mock_db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=operation))

        with patch("app.services.ai.get_prompt") as mock_get_prompt, \
             patch("app.services.ai.call_llm") as mock_call_llm, \
             patch("app.services.ai.calculate_cost") as mock_calc_cost:
            mock_get_prompt.return_value = "Prompt"
            mock_call_llm.side_effect = ValueError("Insufficient balance")
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


# ---------------------------------------------------------------------------
# Additional tests for missing coverage
# ---------------------------------------------------------------------------


class TestCallLLMModelRegistration:
    """Test call_llm requires explicit provider model registration."""

    @pytest.mark.asyncio
    async def test_unregistered_openai_model_raises(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="openai_compatible",
            api_key="test-key",
            base_url=None,
            models=["gpt-4o"],
            is_active=True,
        )

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        runtime_cfg = {
            "llm_request_timeout_seconds": 180,
            "llm_retry_count": 4,
            "llm_retry_interval_seconds": 2.0,
            "llm_prefer_stream": False,
        }

        with patch("app.services.ai._load_llm_runtime_config", AsyncMock(return_value=runtime_cfg)):
            with pytest.raises(ValueError, match='No active provider has registered model "gpt-4-turbo"'):
                await call_llm("gpt-4-turbo", "Test prompt", mock_db)

    @pytest.mark.asyncio
    async def test_unregistered_anthropic_model_raises(self, mock_db: AsyncMock):
        from app.services.ai import call_llm

        config = SimpleNamespace(
            provider="anthropic_compatible",
            api_key="ant-key",
            base_url=None,
            models=["claude-3-opus"],
            is_active=True,
        )

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [config]
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        with pytest.raises(ValueError, match='No active provider has registered model "claude-3-5-sonnet"'):
            await call_llm("claude-3-5-sonnet", "Test", mock_db)



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
        """Verify operation uses cost already recorded by call_llm."""
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
        project = SimpleNamespace(id="proj-1", content="Project text", chapters=[])
        user = SimpleNamespace(id="user-1", balance=Decimal("50.00"))

        mock_db.execute.return_value = MagicMock(
            scalar_one=MagicMock(return_value=operation)
        )

        with patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value={}), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.ai.calculate_cost", new_callable=AsyncMock) as mock_cost, \
             patch("app.services.creative_memory.build_creative_memory_pack", new_callable=AsyncMock, return_value={}):
            mock_llm.return_value = {
                "content": "Output text",
                "input_tokens": 200,
                "output_tokens": 100,
                "cost": Decimal("0.10"),
                "usage_recorded": True,
            }
            mock_cost.return_value = Decimal("0.10")

            result = await run_operation("op-1", project, user, "CREATE", "Input", "gpt-4o-mini", mock_db)

        assert result.status == "COMPLETED"
        assert result.output == "Output text"
        assert result.input_tokens == 200
        assert result.output_tokens == 100
        assert result.cost == Decimal("0.10")


class TestRunOperationCreativeMemoryException:
    """Test run_operation when creative memory enhancement raises (lines 203-204)."""

    @pytest.mark.asyncio
    async def test_creative_memory_exception_marks_operation_failed(self, mock_db: AsyncMock):
        """Enhancement failure is visible instead of silently bypassing RAG."""
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
        project = SimpleNamespace(id="proj-1", content="text", chapters=[])
        user = SimpleNamespace(id="user-1", balance=Decimal("10.00"))

        mock_db.execute.return_value = MagicMock(
            scalar_one=MagicMock(return_value=operation)
        )

        with patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value={}), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.ai.calculate_cost", new_callable=AsyncMock, return_value=Decimal("0.01")), \
             patch("app.services.creative_memory.build_creative_memory_pack", new_callable=AsyncMock, side_effect=RuntimeError("creative memory down")):
            mock_llm.return_value = {"content": "OK", "input_tokens": 10, "output_tokens": 5}

            result = await run_operation("op-2", project, user, "CONTINUE", "inp", "gpt-4o-mini", mock_db)

        assert result.status == "FAILED"
        assert result.error == "creative memory down"
        mock_llm.assert_not_awaited()


class TestRunOperationChapterFinalize:
    @pytest.mark.asyncio
    async def test_agent_task_applies_agent_workspace(self, mock_db: AsyncMock):
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-agent",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
            metadata_={},
        )
        project = SimpleNamespace(id="proj-1", content="", chapters=[], creative_state={})
        user = SimpleNamespace(id="user-1", balance=Decimal("10.00"))
        payload = {
            "task_kind": "ingest_analysis",
            "text_type": "product_intro",
            "memory_schema": {"entity_types": ["Feature", "Audience"]},
            "structured_memory": {"features": ["多模型网关"]},
            "graph": {"nodes": [{"id": "feature:gateway", "type": "Feature", "name": "多模型网关"}], "edges": []},
            "retrieval_queries": ["产品目标用户"],
            "writing_plan": ["提炼卖点", "生成章节"],
            "output": "已完成结构化拆解。",
        }

        with patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.memory_backend.writeback_agent", new_callable=AsyncMock) as mock_writeback, \
             patch("app.services.creative_memory.build_creative_memory_pack", new_callable=AsyncMock, return_value={}), \
             patch("app.services.ai.write_project_workspace_version_snapshot_from_db", new_callable=AsyncMock) as snapshot_mock:
            mock_writeback.return_value = {
                "memory_id": "memory-1",
                "added_memory_id": "agent-memory-1",
                "structured_memory": True,
                "graph_nodes": 1,
                "graph_edges": 0,
            }
            mock_llm.return_value = {
                "content": json.dumps(payload, ensure_ascii=False),
                "input_tokens": 20,
                "output_tokens": 30,
                "cost": Decimal("0.02"),
                "usage_recorded": True,
            }

            result = await run_operation(
                operation_id="op-agent",
                project=project,
                user=user,
                op_type="AGENT_TASK",
                input_text="分析这个产品介绍项目",
                model="gpt-4o-mini",
                db=mock_db,
                loaded_operation=operation,
            )

        assert result.status == "COMPLETED"
        assert project.creative_state["agent_workspace"]["text_type"] == "product_intro"
        assert project.creative_state["agent_workspace"]["structured_memory"]["features"] == ["多模型网关"]
        assert operation.metadata_["agent_state_update"]["raw_output_only"] is False
        assert operation.metadata_["agent_memory_writeback"]["added_memory_id"] == "agent-memory-1"
        mock_writeback.assert_awaited_once()
        assert mock_writeback.await_args.args[:2] == ("proj-1", payload)
        assert mock_writeback.await_args.kwargs["operation_id"] == "op-agent"
        assert mock_writeback.await_args.kwargs["operation_type"] == "AGENT_TASK"
        assert mock_writeback.await_args.kwargs["source_text"] == "分析这个产品介绍项目"
        assert mock_llm.await_args.kwargs["max_tokens"] == 16384
        snapshot_mock.assert_awaited_once_with(project, mock_db, "Apply AGENT_TASK result")

    @pytest.mark.asyncio
    async def test_agent_suggest_accepts_free_text_output(self, mock_db: AsyncMock):
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-agent-suggest",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
            metadata_={},
        )
        project = SimpleNamespace(id="proj-1", content="", chapters=[], creative_state={})
        user = SimpleNamespace(id="user-1", balance=Decimal("10.00"))

        with patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.memory_backend.writeback_agent", new_callable=AsyncMock) as mock_writeback, \
             patch("app.services.creative_memory.build_creative_memory_pack", new_callable=AsyncMock, return_value={}):
            mock_llm.return_value = {
                "content": "下一句可以承接主角对钥匙的触感描写。",
                "input_tokens": 20,
                "output_tokens": 30,
                "cost": Decimal("0.02"),
                "usage_recorded": True,
            }

            result = await run_operation(
                operation_id="op-agent-suggest",
                project=project,
                user=user,
                op_type="AGENT_SUGGEST",
                input_text="当前光标前文本",
                model="gpt-4o-mini",
                db=mock_db,
                loaded_operation=operation,
            )

        assert result.status == "COMPLETED"
        assert result.output == "下一句可以承接主角对钥匙的触感描写。"
        assert operation.metadata_["agent_state_update"]["raw_output_only"] is True
        mock_writeback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_agent_task_can_update_workspace_without_cognee_writeback(self, mock_db: AsyncMock):
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-agent-plan",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
            metadata_={
                "agent_memory_writeback_mode": "workspace_only",
                "agent_memory_writeback_reason": "plan only",
            },
        )
        project = SimpleNamespace(id="proj-1", content="", chapters=[], creative_state={})
        user = SimpleNamespace(id="user-1", balance=Decimal("10.00"))
        payload = {
            "task_kind": "document_plan",
            "text_type": "novel",
            "writing_plan": [{"title": "第一章"}],
            "output": "规划完成",
        }

        with patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.memory_backend.writeback_agent", new_callable=AsyncMock) as mock_writeback, \
             patch("app.services.creative_memory.build_creative_memory_pack", new_callable=AsyncMock, return_value={}), \
             patch("app.services.ai.write_project_workspace_version_snapshot_from_db", new_callable=AsyncMock) as snapshot_mock:
            mock_llm.return_value = {
                "content": json.dumps(payload, ensure_ascii=False),
                "input_tokens": 20,
                "output_tokens": 30,
                "cost": Decimal("0.02"),
                "usage_recorded": True,
            }

            result = await run_operation(
                operation_id="op-agent-plan",
                project=project,
                user=user,
                op_type="AGENT_TASK",
                input_text="规划长篇",
                model="gpt-4o-mini",
                db=mock_db,
                loaded_operation=operation,
            )

        assert result.status == "COMPLETED"
        assert project.creative_state["agent_workspace"]["writing_plan"] == [{"title": "第一章"}]
        assert operation.metadata_["agent_memory_writeback"] == {
            "mode": "workspace_only",
            "skipped": True,
            "reason": "plan only",
        }
        mock_writeback.assert_not_awaited()
        snapshot_mock.assert_awaited_once_with(project, mock_db, "Apply AGENT_TASK result")

    @pytest.mark.asyncio
    async def test_agent_document_content_does_not_store_full_content_in_workspace(self, mock_db: AsyncMock):
        from app.services.ai import run_operation

        operation = SimpleNamespace(
            id="op-agent-unit",
            status="PENDING",
            progress=0,
            message="",
            output=None,
            input_tokens=None,
            output_tokens=None,
            cost=None,
            error=None,
            metadata_={"agent_memory_writeback_mode": "workspace_only"},
        )
        project = SimpleNamespace(id="proj-1", content="", chapters=[], creative_state={})
        user = SimpleNamespace(id="user-1", balance=Decimal("10.00"))
        chapter_text = "本章正文" * 200
        payload = {
            "unit_title": "第十二章",
            "content": chapter_text,
            "structured_memory": {"new_facts": ["沈砚确认旧庙街坐标"]},
            "graph": {"nodes": [{"id": "EV-012", "type": "Event", "name": "旧庙街定位"}], "edges": []},
            "retrieval_queries": ["旧庙街 坐标"],
            "next_actions": ["下一章推进旧庙街调查"],
        }

        with patch("app.services.ai.get_prompt", new_callable=AsyncMock, return_value="Prompt"), \
             patch("app.services.ai.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.services.memory_backend.writeback_agent", new_callable=AsyncMock) as mock_writeback, \
             patch("app.services.creative_memory.build_creative_memory_pack", new_callable=AsyncMock, return_value={}), \
             patch("app.services.ai.write_project_workspace_version_snapshot_from_db", new_callable=AsyncMock) as snapshot_mock:
            mock_llm.return_value = {
                "content": json.dumps(payload, ensure_ascii=False),
                "input_tokens": 20,
                "output_tokens": 30,
                "cost": Decimal("0.02"),
                "usage_recorded": True,
            }

            result = await run_operation(
                operation_id="op-agent-unit",
                project=project,
                user=user,
                op_type="AGENT_TASK",
                input_text="写第十二章",
                model="gpt-4o-mini",
                db=mock_db,
                loaded_operation=operation,
            )

        assert result.status == "COMPLETED"
        workspace = project.creative_state["agent_workspace"]
        assert workspace["last_task"]["unit_title"] == "第十二章"
        assert workspace["last_task"]["content_chars"] == len(chapter_text)
        assert "content" not in workspace["last_task"]
        assert workspace["last_document_unit"] == workspace["last_task"]
        assert operation.output == json.dumps(payload, ensure_ascii=False)
        assert operation.metadata_["agent_state_update"]["workspace_compacted"] is True
        mock_writeback.assert_not_awaited()
        snapshot_mock.assert_awaited_once_with(project, mock_db, "Apply AGENT_TASK result")

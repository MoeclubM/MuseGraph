from __future__ import annotations

import asyncio
import sys
from enum import Enum
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest
from pydantic import BaseModel

from app.services import graphiti_graph


@pytest.fixture(autouse=True)
def _reset_graphiti_setup_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(graphiti_graph, "_GRAPHITI_SETUP_COMPLETE", set())
    yield


def _fake_import_runtime():
    class Graphiti:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class KuzuDriver:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def build_indices_and_constraints(self):
            return None

        async def close(self):
            return None

    class EpisodeType(Enum):
        text = "text"

    class OpenAIGenericClient:
        def __init__(self, config=None, cache=False, client=None, max_tokens=16384):
            self.config = config
            self.client = client
            self.model = getattr(config, "model", None)
            self.temperature = getattr(config, "temperature", 0)
            self.max_tokens = max_tokens
            self.MAX_RETRIES = 1

        def _clean_input(self, value):
            return value

    class OpenAIEmbedder:
        def __init__(self, config=None):
            self.config = config

    class OpenAIEmbedderConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class LLMConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class OpenAIRerankerClient:
        def __init__(self, config=None):
            self.config = config

    recipes = {
        "combined_rrf": SimpleNamespace(model_copy=lambda deep=True: SimpleNamespace(limit=10)),
        "edge_rrf": SimpleNamespace(model_copy=lambda deep=True: SimpleNamespace(limit=10)),
        "node_rrf": SimpleNamespace(model_copy=lambda deep=True: SimpleNamespace(limit=10)),
    }
    return Graphiti, KuzuDriver, OpenAIGenericClient, LLMConfig, OpenAIEmbedder, OpenAIEmbedderConfig, OpenAIRerankerClient, EpisodeType, recipes


def _runtime_selection() -> graphiti_graph._GraphitiRuntimeSelection:
    return graphiti_graph._GraphitiRuntimeSelection(
        llm_provider_type="openai_compatible",
        llm_model="chat-model",
        llm_api_key="llm-key",
        llm_base_url="https://example.com/v1",
        embedding_model="embed-model",
        embedding_api_key="embed-key",
        embedding_base_url="https://example.com/v1",
        reranker_model="reranker-model",
        reranker_api_key="reranker-key",
        reranker_base_url="https://example-reranker.com/v1",
        timeout_seconds=120,
        retry_count=1,
        max_coroutines=2,
        reasoning_effort=None,
        chunk_size=4000,
        chunk_overlap=160,
        llm_max_tokens=16384,
        openai_api_style="responses",
    )


def test_patch_graphiti_driver_compatibility_sets_database_and_clone():
    driver = SimpleNamespace()
    patched = graphiti_graph._patch_graphiti_driver_compatibility(driver)

    assert patched._database == ""
    assert patched.clone(database="graph-1") is patched
    assert patched._database == "graph-1"


def test_graphiti_request_timeout_seconds_adds_margin():
    assert graphiti_graph._graphiti_request_timeout_seconds(120) == 240
    assert graphiti_graph._graphiti_request_timeout_seconds(180) == 300


def test_graphiti_episode_timeout_seconds_scales_above_request_timeout():
    assert graphiti_graph._graphiti_episode_timeout_seconds(120) == 360
    assert graphiti_graph._graphiti_episode_timeout_seconds(180) == 450


def test_graphiti_store_io_error_detects_missing_catalog_table():
    exc = RuntimeError("Runtime exception: Load table failed: table 3833738872973833261 doesn't exist in catalog.")

    assert graphiti_graph._is_graphiti_store_io_error(exc) is True


def test_split_text_prefers_sentence_boundaries_for_dense_text():
    text = " ".join(f"Sentence {index} ends here." for index in range(1, 80))

    chunks = graphiti_graph._split_text(text, chunk_size=240, overlap=24)

    assert len(chunks) > 3
    assert all(len(chunk) <= 264 for chunk in chunks)
    assert any(chunk.endswith(".") for chunk in chunks[:-1])


def test_normalize_graphiti_chunk_config_clamps_overlap():
    chunk_size, chunk_overlap = graphiti_graph.normalize_graphiti_chunk_config(
        {"graphiti_chunk_size": 1000, "graphiti_chunk_overlap": 900}
    )

    assert chunk_size == 1000
    assert chunk_overlap == 250


@pytest.mark.asyncio
async def test_build_graph_uses_runtime_chunk_config(monkeypatch: pytest.MonkeyPatch):
    add_episode = AsyncMock(return_value=SimpleNamespace(episode=SimpleNamespace(uuid="ep-1")))
    fake_graphiti = SimpleNamespace(
        add_episode=add_episode,
        build_indices_and_constraints=AsyncMock(),
        close=AsyncMock(),
    )
    runtime = _runtime_selection()
    runtime.chunk_size = 240
    runtime.chunk_overlap = 0

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", graph_id="graph-existing")),
    )
    monkeypatch.setattr(graphiti_graph, "_import_graphiti_runtime", _fake_import_runtime)

    await graphiti_graph.build_graph("proj-1", "A" * 700, db=AsyncMock())

    assert add_episode.await_count == 3


@pytest.mark.asyncio
async def test_patch_graphiti_driver_compatibility_swallows_existing_fulltext_index_error():
    class _Client:
        async def execute(self, query, parameters=None):
            raise RuntimeError("Binder exception: Index node_name_and_summary already exists in table Entity.")

    driver = SimpleNamespace(client=_Client())
    patched = graphiti_graph._patch_graphiti_driver_compatibility(driver)

    rows, _, _ = await patched.execute_query(
        "CALL CREATE_FTS_INDEX('Entity', 'node_name_and_summary', ['name', 'summary']);"
    )

    assert rows == []


@pytest.mark.asyncio
async def test_setup_graphiti_releases_driver_reference_after_close(monkeypatch: pytest.MonkeyPatch, tmp_path):
    created: dict[str, object] = {}

    class FakeKuzuDriver:
        def __init__(self, *args, **kwargs):
            created["driver"] = self

        async def build_indices_and_constraints(self):
            created["built"] = True

        async def execute_query(self, *args, **kwargs):
            return [], None, None

        async def close(self):
            created["closed"] = True

    monkeypatch.setattr(
        graphiti_graph,
        "_import_graphiti_runtime",
        lambda: (
            object,
            FakeKuzuDriver,
            object,
            object,
            object,
            object,
            object,
            SimpleNamespace,
            {},
        ),
    )
    monkeypatch.setattr(
        graphiti_graph.settings,
        "GRAPHITI_DB_PATH",
        str(tmp_path / "graphiti" / "graphiti.kuzu"),
        raising=False,
    )
    collect_mock = MagicMock(return_value=0)
    monkeypatch.setattr(graphiti_graph.gc, "collect", collect_mock)

    await graphiti_graph.setup_graphiti("proj-1")

    assert created["closed"] is True
    collect_mock.assert_called_once()


@pytest.mark.asyncio
async def test_patch_graphiti_llm_client_propagates_transient_connection_error_without_internal_retry():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    class _FakeResponses:
        def __init__(self):
            self.calls: list[dict] = []

        async def parse(self, **kwargs):
            self.calls.append(kwargs)
            raise openai.APIConnectionError(
                message="Connection error.",
                request=httpx.Request("POST", "https://example.com/v1/responses"),
            )

    class _DummyBase:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(responses=_FakeResponses())
            self.model = "chat-model"
            self.temperature = 0
            self.max_tokens = 16384
            self.MAX_RETRIES = 1
            self.config = SimpleNamespace(base_url="https://example.com/v1", timeout_seconds=77)

        def _clean_input(self, value):
            return value

    patched_cls = graphiti_graph._patch_graphiti_llm_client(_DummyBase)
    client = patched_cls()

    with pytest.raises(openai.APIConnectionError):
        await client._generate_response(
            [SimpleNamespace(role="user", content="Return entities only.")],
            response_model=ExtractedEntities,
            max_tokens=16384,
        )

    assert len(client.client.responses.calls) == 1
    assert client.client.responses.calls[0]["text_format"] is ExtractedEntities
    assert client.client.responses.calls[0]["timeout"] == 77
    assert client.client.responses.calls[0]["max_output_tokens"] == 16384


@pytest.mark.asyncio
async def test_patch_graphiti_llm_client_passes_reasoning_effort_for_gpt5():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    class _FakeResponses:
        def __init__(self):
            self.calls: list[dict] = []

        async def parse(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(output_parsed={"extracted_entities": []}, output_text='{"extracted_entities":[]}')

    class _DummyBase:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(responses=_FakeResponses())
            self.model = "gpt-5.4"
            self.temperature = 0
            self.max_tokens = 16384
            self.MAX_RETRIES = 1
            self.config = SimpleNamespace(
                base_url="https://example.com/v1",
                timeout_seconds=77,
                reasoning_effort="minimal",
            )

        def _clean_input(self, value):
            return value

    patched_cls = graphiti_graph._patch_graphiti_llm_client(_DummyBase)
    client = patched_cls()

    await client._generate_response(
        [SimpleNamespace(role="user", content="Return entities only.")],
        response_model=ExtractedEntities,
        max_tokens=16384,
    )

    assert client.client.responses.calls[0]["reasoning"] == {"effort": "minimal"}


@pytest.mark.asyncio
async def test_patch_graphiti_llm_client_passes_reasoning_effort_for_gpt54_compact():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    class _FakeResponses:
        def __init__(self):
            self.calls: list[dict] = []

        async def parse(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(output_parsed={"extracted_entities": []}, output_text='{"extracted_entities":[]}')

    class _DummyBase:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(responses=_FakeResponses())
            self.model = "gpt-5.4-openai-compact"
            self.temperature = 0
            self.max_tokens = 16384
            self.MAX_RETRIES = 1
            self.config = SimpleNamespace(
                base_url="https://example.com/v1",
                timeout_seconds=77,
                reasoning_effort="none",
            )

        def _clean_input(self, value):
            return value

    patched_cls = graphiti_graph._patch_graphiti_llm_client(_DummyBase)
    client = patched_cls()

    await client._generate_response(
        [SimpleNamespace(role="user", content="Return entities only.")],
        response_model=ExtractedEntities,
        max_tokens=16384,
    )

    assert client.client.responses.calls[0]["reasoning"] == {"effort": "none"}


@pytest.mark.asyncio
async def test_patch_graphiti_llm_client_retries_when_parsed_json_fails_validation():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    class _FakeResponses:
        def __init__(self):
            self.calls: list[dict] = []

        async def parse(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(output_parsed=None, output_text='{"foo":"bar"}')

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                output_text='{"extracted_entities":[{"name":"Alice","entity_type_id":1}]}'
            )

    class _DummyBase:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(responses=_FakeResponses())
            self.model = "chat-model"
            self.temperature = 0
            self.max_tokens = 16384
            self.MAX_RETRIES = 1
            self.config = SimpleNamespace(base_url="https://example.com/v1", timeout_seconds=77)

        def _clean_input(self, value):
            return value

    patched_cls = graphiti_graph._patch_graphiti_llm_client(_DummyBase)
    client = patched_cls()

    result = await client._generate_response(
        [SimpleNamespace(role="user", content="Return entities only.")],
        response_model=ExtractedEntities,
        max_tokens=16384,
    )

    assert result == {"extracted_entities": [{"name": "Alice", "entity_type_id": 1}]}
    assert len(client.client.responses.calls) == 2
    assert client.client.responses.calls[0]["text_format"] is ExtractedEntities
    assert client.client.responses.calls[1]["text"]["format"]["type"] == "json_object"


@pytest.mark.asyncio
async def test_patch_graphiti_llm_client_uses_chat_json_mode_when_configured():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    async def _stream():
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content='{"extracted_entities":'))],
            usage=None,
        )
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="[]}"))],
            usage={"prompt_tokens": 20, "completion_tokens": 7},
        )

    class _FakeChatCompletions:
        def __init__(self):
            self.calls: list[dict] = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return _stream()

    class _DummyBase:
        def __init__(self, *args, **kwargs):
            completions = _FakeChatCompletions()
            self.client = SimpleNamespace(
                chat=SimpleNamespace(completions=completions),
                responses=SimpleNamespace(parse=AsyncMock(), create=AsyncMock()),
            )
            self.model = "LongCat-Flash-Lite"
            self.temperature = 0
            self.max_tokens = 16384
            self.MAX_RETRIES = 1
            self.config = SimpleNamespace(
                base_url="https://newapi.telecom.moe/v1",
                timeout_seconds=77,
                reasoning_effort="low",
                openai_api_style="chat_completions",
            )

        def _clean_input(self, value):
            return value

    patched_cls = graphiti_graph._patch_graphiti_llm_client(_DummyBase)
    client = patched_cls()

    result = await client._generate_response(
        [SimpleNamespace(role="user", content="Return entities only.")],
        response_model=ExtractedEntities,
        max_tokens=16384,
    )

    call = client.client.chat.completions.calls[0]
    assert result == {"extracted_entities": []}
    assert call["response_format"] == {"type": "json_object"}
    assert "extra_body" not in call
    assert "reasoning_effort" not in call
    assert call["stream"] is True
    assert "EXAMPLE JSON OUTPUT" in call["messages"][-1]["content"]
    assert client.client.responses.parse.await_count == 0
    assert client.client.responses.create.await_count == 0


@pytest.mark.asyncio
async def test_patch_graphiti_llm_client_enables_deepseek_thinking_in_chat_mode():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    class _FakeChatCompletions:
        def __init__(self):
            self.calls: list[dict] = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"extracted_entities":[]}'))]
            )

    class _DummyBase:
        def __init__(self, *args, **kwargs):
            completions = _FakeChatCompletions()
            self.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
            self.model = "deepseek-v4-flash"
            self.temperature = 0
            self.max_tokens = 16384
            self.MAX_RETRIES = 1
            self.config = SimpleNamespace(
                base_url="https://newapi.telecom.moe/v1",
                timeout_seconds=77,
                reasoning_effort="low",
                openai_api_style="chat_completions",
            )

        def _clean_input(self, value):
            return value

    patched_cls = graphiti_graph._patch_graphiti_llm_client(_DummyBase)
    client = patched_cls()

    result = await client._generate_response(
        [SimpleNamespace(role="user", content="Return entities only.")],
        response_model=ExtractedEntities,
        max_tokens=16384,
    )

    call = client.client.chat.completions.calls[0]
    assert result == {"extracted_entities": []}
    assert call["extra_body"] == {"thinking": {"type": "enabled"}}
    assert call["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_patch_graphiti_llm_client_accepts_nonstream_gateway_response_for_deepseek():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    class _FakeChatCompletions:
        def __init__(self):
            self.calls: list[dict] = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"extracted_entities":[]}'))]
            )

    class _DummyBase:
        def __init__(self, *args, **kwargs):
            completions = _FakeChatCompletions()
            self.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
            self.model = "deepseek-v4-flash"
            self.temperature = 0
            self.max_tokens = 16384
            self.MAX_RETRIES = 1
            self.config = SimpleNamespace(
                base_url="https://newapi.telecom.moe/v1",
                timeout_seconds=77,
                reasoning_effort="low",
                openai_api_style="chat_completions",
            )

        def _clean_input(self, value):
            return value

    patched_cls = graphiti_graph._patch_graphiti_llm_client(_DummyBase)
    client = patched_cls()

    result = await client._generate_response(
        [SimpleNamespace(role="user", content="Return entities only.")],
        response_model=ExtractedEntities,
        max_tokens=16384,
    )

    call = client.client.chat.completions.calls[0]
    assert result == {"extracted_entities": []}
    assert call["stream"] is True


@pytest.mark.asyncio
async def test_patch_graphiti_llm_client_propagates_gateway_504_without_internal_retry():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    class GatewayTimeoutError(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.status_code = 504

    class _FakeResponses:
        def __init__(self):
            self.calls: list[dict] = []

        async def parse(self, **kwargs):
            self.calls.append(kwargs)
            raise GatewayTimeoutError("<!DOCTYPE html><title>504 Gateway Time-out</title>")

    class _DummyBase:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(responses=_FakeResponses())
            self.model = "chat-model"
            self.temperature = 0
            self.max_tokens = 16384
            self.MAX_RETRIES = 1
            self.config = SimpleNamespace(base_url="https://example.com/v1", timeout_seconds=77)

        def _clean_input(self, value):
            return value

    patched_cls = graphiti_graph._patch_graphiti_llm_client(_DummyBase)
    client = patched_cls()

    with pytest.raises(GatewayTimeoutError):
        await client._generate_response(
            [SimpleNamespace(role="user", content="Return entities only.")],
            response_model=ExtractedEntities,
            max_tokens=16384,
        )

    assert len(client.client.responses.calls) == 1
    assert client.client.responses.calls[0]["text_format"] is ExtractedEntities


@pytest.mark.asyncio
async def test_create_graphiti_disables_internal_retries_and_applies_token_cap(monkeypatch: pytest.MonkeyPatch, tmp_path):
    created: dict[str, object] = {}

    class FakeGraphiti:
        def __init__(self, **kwargs):
            created.update(kwargs)

    class FakeKuzuDriver:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def execute_query(self, *args, **kwargs):
            return None

    class FakeLLMConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeEmbedderConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeOpenAIGenericClient:
        def __init__(self, config=None, cache=False, client=None, max_tokens=16384):
            self.config = config
            self.model = getattr(config, "model", None)
            self.temperature = getattr(config, "temperature", 0)
            self.max_tokens = max_tokens
            self.client = client
            self.MAX_RETRIES = 2

        def _clean_input(self, value):
            return value

    class FakeOpenAIEmbedder:
        def __init__(self, config=None):
            self.config = config

    class FakeOpenAIRerankerClient:
        def __init__(self, config=None):
            self.config = config

    monkeypatch.setattr(
        graphiti_graph,
        "_import_graphiti_runtime",
        lambda: (
            FakeGraphiti,
            FakeKuzuDriver,
            FakeOpenAIGenericClient,
            FakeLLMConfig,
            FakeOpenAIEmbedder,
            FakeEmbedderConfig,
            FakeOpenAIRerankerClient,
            SimpleNamespace,
            {},
        ),
    )
    monkeypatch.setattr(
        graphiti_graph.settings,
        "GRAPHITI_DB_PATH",
        str(tmp_path / "graphiti" / "graphiti.kuzu"),
        raising=False,
    )

    await graphiti_graph._create_graphiti(runtime=_runtime_selection(), project_id="proj-1")

    llm_client = created["llm_client"]
    cross_encoder = created["cross_encoder"]
    assert llm_client.max_tokens == 16384
    assert llm_client.MAX_RETRIES == 0
    assert getattr(llm_client.config, "timeout_seconds") == graphiti_graph._graphiti_request_timeout_seconds(120)
    assert getattr(cross_encoder.config, "model") == "reranker-model"
    assert getattr(cross_encoder.config, "api_key") == "reranker-key"
    assert getattr(cross_encoder.config, "base_url") == "https://example-reranker.com/v1"
    assert getattr(cross_encoder.config, "timeout_seconds") == graphiti_graph._graphiti_request_timeout_seconds(120)


@pytest.mark.asyncio
async def test_create_graphiti_uses_anthropic_llm_client_when_runtime_provider_is_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    created: dict[str, object] = {}

    class FakeGraphiti:
        def __init__(self, **kwargs):
            created.update(kwargs)

    class FakeKuzuDriver:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def execute_query(self, *args, **kwargs):
            return None

    class FakeLLMConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeEmbedderConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeOpenAIGenericClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("OpenAI LLM client should not be created for anthropic runtime")

    class FakeOpenAIEmbedder:
        def __init__(self, config=None):
            self.config = config

    class FakeOpenAIRerankerClient:
        def __init__(self, config=None):
            self.config = config

    class FakeAnthropicSDKClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeAnthropicGraphitiClient:
        def __init__(self, config=None, client=None, max_tokens=16384):
            self.config = config
            self.client = client
            self.max_tokens = max_tokens

        def _clean_input(self, value):
            return value

    monkeypatch.setattr(
        graphiti_graph,
        "_import_graphiti_runtime",
        lambda: (
            FakeGraphiti,
            FakeKuzuDriver,
            FakeOpenAIGenericClient,
            FakeLLMConfig,
            FakeOpenAIEmbedder,
            FakeEmbedderConfig,
            FakeOpenAIRerankerClient,
            SimpleNamespace,
            {},
        ),
    )
    monkeypatch.setattr(
        graphiti_graph.settings,
        "GRAPHITI_DB_PATH",
        str(tmp_path / "graphiti" / "graphiti.kuzu"),
        raising=False,
    )

    anthropic_sdk_module = ModuleType("anthropic")
    anthropic_sdk_module.AsyncAnthropic = FakeAnthropicSDKClient
    anthropic_graphiti_module = ModuleType("graphiti_core.llm_client.anthropic_client")
    anthropic_graphiti_module.AnthropicClient = FakeAnthropicGraphitiClient
    monkeypatch.setitem(sys.modules, "anthropic", anthropic_sdk_module)
    monkeypatch.setitem(sys.modules, "graphiti_core.llm_client.anthropic_client", anthropic_graphiti_module)

    runtime = graphiti_graph._GraphitiRuntimeSelection(
        llm_provider_type="anthropic_compatible",
        llm_model="claude-3-5-sonnet",
        llm_api_key="anthropic-key",
        llm_base_url="https://anthropic-proxy.example/v1",
        embedding_model="embed-model",
        embedding_api_key="embed-key",
        embedding_base_url="https://example.com/v1",
        reranker_model="reranker-model",
        reranker_api_key="reranker-key",
        reranker_base_url="https://example-reranker.com/v1",
        timeout_seconds=120,
        retry_count=1,
        max_coroutines=2,
        reasoning_effort=None,
        chunk_size=4000,
        chunk_overlap=160,
        llm_max_tokens=16384,
        openai_api_style="responses",
    )

    await graphiti_graph._create_graphiti(runtime=runtime, project_id="proj-1")

    llm_client = created["llm_client"]
    assert isinstance(llm_client, FakeAnthropicGraphitiClient)
    assert getattr(llm_client.config, "model") == "claude-3-5-sonnet"
    assert getattr(llm_client.config, "base_url") == "https://anthropic-proxy.example/v1"
    assert getattr(llm_client.client, "kwargs") == {
        "api_key": "anthropic-key",
        "base_url": "https://anthropic-proxy.example/v1",
        "max_retries": 1,
    }


@pytest.mark.asyncio
async def test_resolve_graphiti_runtime_allows_anthropic_llm_with_openai_embedding_and_reranker(
    monkeypatch: pytest.MonkeyPatch,
):
    project = SimpleNamespace(
        component_models={
            "graph_build": "claude-3-5-sonnet",
            "graph_embedding": "text-embedding-3-small",
            "graph_reranker": "bge-reranker-v2-m3",
        }
    )
    anthropic_provider = SimpleNamespace(
        provider="anthropic_compatible",
        api_key="anthropic-key",
        base_url="https://anthropic-proxy.example/v1",
        models=["claude-3-5-sonnet"],
        is_active=True,
        name="Anthropic Gateway",
    )
    openai_provider = SimpleNamespace(
        provider="openai_compatible",
        api_key="openai-key",
        base_url="https://openai-proxy.example/v1",
        models={
            "models": ["gpt-4.1-mini"],
            "embedding_models": ["text-embedding-3-small"],
            "reranker_models": ["bge-reranker-v2-m3"],
        },
        is_active=True,
        name="OpenAI Gateway",
    )
    db = AsyncMock()
    result_mock = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [anthropic_provider, openai_provider])
    )
    db.execute.return_value = result_mock
    monkeypatch.setattr(graphiti_graph, "_load_project", AsyncMock(return_value=project))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_llm_runtime_config",
        AsyncMock(
            return_value={
                "llm_task_concurrency": 4,
                "llm_request_timeout_seconds": 180,
                "llm_retry_count": 2,
                "llm_reasoning_effort": "high",
            }
        ),
    )

    runtime = await graphiti_graph._resolve_graphiti_runtime(project_id="proj-1", db=db)

    assert runtime.llm_provider_type == "anthropic_compatible"
    assert runtime.llm_model == "claude-3-5-sonnet"
    assert runtime.llm_base_url == "https://anthropic-proxy.example/v1"
    assert runtime.embedding_model == "text-embedding-3-small"
    assert runtime.embedding_base_url == "https://openai-proxy.example/v1"
    assert runtime.reranker_model == "bge-reranker-v2-m3"
    assert runtime.reranker_base_url == "https://openai-proxy.example/v1"
    assert runtime.reasoning_effort == "high"


@pytest.mark.asyncio
async def test_patch_graphiti_driver_compatibility_builds_kuzu_fulltext_indices():
    original_execute_query = AsyncMock()
    driver = SimpleNamespace(execute_query=original_execute_query)
    patched = graphiti_graph._patch_graphiti_driver_compatibility(driver)

    await patched.build_indices_and_constraints()

    created_queries = [call.args[0] for call in original_execute_query.await_args_list]
    assert any("node_name_and_summary" in query for query in created_queries)
    assert any("episode_content" in query for query in created_queries)


def test_parse_graphiti_response_content_salvages_fenced_json():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    raw = """
Here is the structured result:

```json
{"nodes":[{"name":"Alice","entity_type_id":1}]}
```
"""

    parsed = graphiti_graph._parse_graphiti_response_content(ExtractedEntities, raw)

    assert parsed == {"nodes": [{"name": "Alice", "entity_type_id": 1}]}


def test_parse_graphiti_response_content_preserves_entity_name_alias_payload():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    raw = '{"extracted_entities":[{"entity_name":"Elena Varga","entity_type_id":1}]}'

    parsed = graphiti_graph._parse_graphiti_response_content(ExtractedEntities, raw)

    assert parsed == {"extracted_entities": [{"entity_name": "Elena Varga", "entity_type_id": 1}]}


def test_parse_graphiti_response_content_rejects_top_level_list():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    raw = '[{"entity_name":"Elena Varga","entity_type_id":1}]'

    with pytest.raises(ValueError):
        graphiti_graph._parse_graphiti_response_content(ExtractedEntities, raw)


def test_parse_graphiti_response_content_rejects_plain_text_single_field():
    class Summary(BaseModel):
        summary: str

    with pytest.raises(ValueError):
        graphiti_graph._parse_graphiti_response_content(
            Summary,
            "Alice leads the core investigation.",
        )


def test_parse_graphiti_response_content_rejects_entity_markdown_table():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    raw = """
## Entity Extraction Results

| Entity | Type | Entity Type ID |
| --- | --- | --- |
| Elena Varga | PERSON | 1 |
| Port Meridian | LOCATION | 2 |
"""

    with pytest.raises(ValueError):
        graphiti_graph._parse_graphiti_response_content(ExtractedEntities, raw)


def test_parse_graphiti_response_content_rejects_edge_duplicate_unstructured_text():
    class EdgeDuplicate(BaseModel):
        duplicate_facts: list[int]
        contradicted_facts: list[int]

    with pytest.raises(ValueError):
        graphiti_graph._parse_graphiti_response_content(
            EdgeDuplicate,
            "No duplicates or contradictions found.",
        )


@pytest.mark.asyncio
async def test_build_graph_uses_existing_graph_id_and_adds_episodes(monkeypatch: pytest.MonkeyPatch):
    async def _add_episode(**kwargs):
        suffix = str(kwargs.get("name") or "").split()[-1]
        return SimpleNamespace(episode=SimpleNamespace(uuid=f"ep-{suffix}"))

    add_episode = AsyncMock(side_effect=_add_episode)
    build_indices = AsyncMock()
    close = AsyncMock()
    fake_graphiti = SimpleNamespace(
        add_episode=add_episode,
        build_indices_and_constraints=build_indices,
        close=close,
    )

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=_runtime_selection()))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", graph_id="graph-existing")),
    )
    monkeypatch.setattr(graphiti_graph, "_import_graphiti_runtime", _fake_import_runtime)

    graph_id = await graphiti_graph.build_graph(
        "proj-1",
        "Alpha\n\nBeta " * 700,
        ontology={
            "entity_types": [{"name": "TIME_POINT", "attributes": [{"name": "role"}]}],
            "edge_types": [{"name": "LOCATED_IN", "source_targets": [{"source": "TIME_POINT", "target": "TIME_POINT"}]}],
        },
        db=AsyncMock(),
    )

    assert graph_id == "graph-existing"
    build_indices.assert_called_once()
    assert add_episode.await_count >= 2
    first_call = add_episode.await_args_list[0].kwargs
    assert first_call["group_id"] == "graph-existing"
    assert "TimePoint" in first_call["entity_types"]
    assert "LocatedIn" in first_call["edge_types"]
    assert first_call["edge_type_map"][("TimePoint", "TimePoint")] == ["LocatedIn"]
    close.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_graph_accepts_ontology_source_type_target_type(monkeypatch: pytest.MonkeyPatch):
    add_episode = AsyncMock(
        return_value=SimpleNamespace(episode=SimpleNamespace(uuid="ep-1"))
    )
    fake_graphiti = SimpleNamespace(
        add_episode=add_episode,
        build_indices_and_constraints=AsyncMock(),
        close=AsyncMock(),
    )

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=_runtime_selection()))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", graph_id="graph-existing")),
    )
    monkeypatch.setattr(graphiti_graph, "_import_graphiti_runtime", _fake_import_runtime)
    monkeypatch.setattr(graphiti_graph, "_split_text", lambda text, **kwargs: ["chunk-1"])

    graph_id = await graphiti_graph.build_graph(
        "proj-1",
        "ignored",
        ontology={
            "entity_types": [{"name": "TIME_POINT", "attributes": [{"name": "role"}]}],
            "edge_types": [{"name": "LOCATED_IN", "source_type": "TIME_POINT", "target_type": "TIME_POINT"}],
        },
        db=AsyncMock(),
    )

    assert graph_id == "graph-existing"
    first_call = add_episode.await_args_list[0].kwargs
    assert "LocatedIn" in first_call["edge_types"]
    assert first_call["edge_type_map"][("TimePoint", "TimePoint")] == ["LocatedIn"]
    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_graph_retries_episode_at_upper_layer(monkeypatch: pytest.MonkeyPatch):
    attempts = {"count": 0}

    async def _add_episode(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise asyncio.TimeoutError("episode timed out")
        return SimpleNamespace(episode=SimpleNamespace(uuid=f"ep-{attempts['count']}"))

    fake_graphiti = SimpleNamespace(
        add_episode=AsyncMock(side_effect=_add_episode),
        build_indices_and_constraints=AsyncMock(),
        close=AsyncMock(),
    )
    progress_messages: list[str] = []

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=_runtime_selection()))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", graph_id="graph-existing")),
    )
    monkeypatch.setattr(graphiti_graph, "_import_graphiti_runtime", _fake_import_runtime)
    monkeypatch.setattr(graphiti_graph, "_split_text", lambda text, **kwargs: ["chunk-1"])

    graph_id = await graphiti_graph.build_graph(
        "proj-1",
        "ignored",
        db=AsyncMock(),
        progress_callback=lambda _progress, message: progress_messages.append(message),
    )

    assert graph_id == "graph-existing"
    assert attempts["count"] == 2
    assert any("retrying in" in message for message in progress_messages)
    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_graph_collects_failed_chunks_when_continue_on_error(monkeypatch: pytest.MonkeyPatch):
    async def _add_episode(**kwargs):
        name = str(kwargs.get("name") or "")
        if name.endswith("2/3"):
            raise RuntimeError("<!DOCTYPE html><html><body><h1>502 Bad Gateway</h1></body></html>")
        suffix = name.split()[-1] if name else "1/3"
        return SimpleNamespace(episode=SimpleNamespace(uuid=f"ep-{suffix}"))

    fake_graphiti = SimpleNamespace(
        add_episode=AsyncMock(side_effect=_add_episode),
        build_indices_and_constraints=AsyncMock(),
        close=AsyncMock(),
    )
    progress_messages: list[str] = []

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=_runtime_selection()))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", graph_id="graph-existing")),
    )
    monkeypatch.setattr(graphiti_graph, "_import_graphiti_runtime", _fake_import_runtime)
    monkeypatch.setattr(graphiti_graph, "_split_text", lambda text, **kwargs: ["chunk-1", "chunk-2", "chunk-3"])

    with pytest.raises(graphiti_graph.GraphBuildPartialFailure) as exc_info:
        await graphiti_graph.build_graph(
            "proj-1",
            "ignored",
            db=AsyncMock(),
            progress_callback=lambda _progress, message: progress_messages.append(message),
            continue_on_error=True,
        )

    partial = exc_info.value
    assert partial.graph_id == "graph-existing"
    assert partial.completed_chunk_indices == [1, 3]
    assert partial.failed_chunk_indices == [2]
    assert partial.selected_chunk_indices == [1, 2, 3]
    assert "502 Bad Gateway" in partial.failed_errors["2"]
    assert any("Continuing with remaining chunks" in message for message in progress_messages)
    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_graph_uses_bounded_parallel_workers_for_small_batch(monkeypatch: pytest.MonkeyPatch):
    active = {"count": 0, "max": 0}

    async def _add_episode(**kwargs):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await asyncio.sleep(0.02)
        active["count"] -= 1
        name = str(kwargs.get("name") or "")
        suffix = name.split()[-1] if name else "1/3"
        return SimpleNamespace(episode=SimpleNamespace(uuid=f"ep-{suffix}"))

    fake_graphiti = SimpleNamespace(
        add_episode=AsyncMock(side_effect=_add_episode),
        build_indices_and_constraints=AsyncMock(),
        close=AsyncMock(),
    )

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=_runtime_selection()))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", graph_id="graph-existing")),
    )
    monkeypatch.setattr(graphiti_graph, "_import_graphiti_runtime", _fake_import_runtime)
    monkeypatch.setattr(graphiti_graph, "_split_text", lambda text, **kwargs: ["chunk-1", "chunk-2", "chunk-3"])

    await graphiti_graph.build_graph("proj-1", "ignored", db=AsyncMock())

    assert active["max"] == 1
    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_graph_scales_parallel_workers_for_large_build(monkeypatch: pytest.MonkeyPatch):
    active = {"count": 0, "max": 0}

    async def _add_episode(**kwargs):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await asyncio.sleep(0.02)
        active["count"] -= 1
        name = str(kwargs.get("name") or "")
        suffix = name.split()[-1] if name else "1/16"
        return SimpleNamespace(episode=SimpleNamespace(uuid=f"ep-{suffix}"))

    fake_graphiti = SimpleNamespace(
        add_episode=AsyncMock(side_effect=_add_episode),
        build_indices_and_constraints=AsyncMock(),
        close=AsyncMock(),
    )
    progress_messages: list[str] = []

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(
        graphiti_graph,
        "_resolve_graphiti_runtime",
        AsyncMock(
            return_value=graphiti_graph._GraphitiRuntimeSelection(
                llm_provider_type="openai_compatible",
                llm_model="chat-model",
                llm_api_key="llm-key",
                llm_base_url="https://example.com/v1",
                embedding_model="embed-model",
                embedding_api_key="embed-key",
                embedding_base_url="https://example.com/v1",
                reranker_model="reranker-model",
                reranker_api_key="reranker-key",
                reranker_base_url="https://example-reranker.com/v1",
                timeout_seconds=120,
                retry_count=1,
                max_coroutines=4,
                reasoning_effort=None,
                chunk_size=4000,
                chunk_overlap=160,
                llm_max_tokens=16384,
                openai_api_style="responses",
            )
        ),
    )
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", graph_id="graph-existing")),
    )
    monkeypatch.setattr(graphiti_graph, "_import_graphiti_runtime", _fake_import_runtime)
    monkeypatch.setattr(
        graphiti_graph,
        "_split_text",
        lambda text, **kwargs: [f"chunk-{index}" for index in range(1, 17)],
    )

    await graphiti_graph.build_graph(
        "proj-1",
        "ignored",
        db=AsyncMock(),
        progress_callback=lambda _progress, message: progress_messages.append(message),
    )

    assert active["max"] == 1
    assert not any("parallel ingest enabled" in message for message in progress_messages)
    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_graph_maps_combined_results(monkeypatch: pytest.MonkeyPatch):
    fake_graphiti = SimpleNamespace(
        search_=AsyncMock(
            return_value=SimpleNamespace(
                edges=[SimpleNamespace(uuid="edge-1", fact="Alice knows Bob", name="Knows")],
                nodes=[SimpleNamespace(uuid="node-1", name="Alice", summary="Lead character", labels=["Entity", "Character"])],
            )
        ),
        close=AsyncMock(),
    )

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=_runtime_selection()))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(graph_id="graph-1")),
    )
    monkeypatch.setattr(graphiti_graph, "_import_graphiti_runtime", _fake_import_runtime)

    results = await graphiti_graph.search_graph(
        "proj-1",
        "who matters",
        db=AsyncMock(),
        top_k=5,
        search_type="GRAPH_COMPLETION",
    )

    assert results[0]["content"] == "Alice knows Bob"
    assert results[1]["type"] == "Character"
    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_graph_visualization_transforms_kuzu_records(monkeypatch: pytest.MonkeyPatch):
    execute_query = AsyncMock(
        side_effect=[
            (
                [
                    {
                        "uuid": "node-1",
                        "name": "Alice",
                        "labels": ["Entity", "Character"],
                        "summary": "hero",
                        "attributes": '{"role":"lead","uuid":"node-1","group_id":"graph-1"}',
                    },
                    {
                        "uuid": "node-2",
                        "name": "Bob",
                        "labels": ["Entity"],
                        "summary": "friend",
                        "attributes": '{"role":"support","group_id":"graph-1"}',
                    },
                ],
                None,
                None,
            ),
            (
                [
                    {
                        "uuid": "edge-1",
                        "source": "node-1",
                        "target": "node-2",
                        "label": "KNOWS",
                        "fact": "Alice knows Bob",
                        "attributes": '{"confidence":"high","group_id":"graph-1"}',
                    }
                ],
                None,
                None,
            ),
        ]
    )
    fake_graphiti = SimpleNamespace(driver=SimpleNamespace(execute_query=execute_query), close=AsyncMock())

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=_runtime_selection()))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(graph_id="graph-1")),
    )

    payload = await graphiti_graph.get_graph_visualization("proj-1", db=AsyncMock())

    assert payload["nodes"][0]["label"] == "Alice"
    assert payload["nodes"][0]["attributes"] == {"role": "lead"}
    assert payload["edges"][0]["source_label"] == "Alice"
    assert payload["edges"][0]["attributes"] == {"confidence": "high"}
    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_graph_visualization_reports_unreadable_kuzu_store(monkeypatch: pytest.MonkeyPatch):
    fake_graphiti = SimpleNamespace(
        driver=SimpleNamespace(
            execute_query=AsyncMock(
                side_effect=RuntimeError(
                    "Runtime exception: Load table failed: table 3833738872973833261 doesn't exist in catalog."
                )
            )
        ),
        close=AsyncMock(),
    )

    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(graphiti_graph, "_resolve_graphiti_runtime", AsyncMock(return_value=_runtime_selection()))
    monkeypatch.setattr(graphiti_graph, "_create_graphiti", AsyncMock(return_value=fake_graphiti))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(graph_id="graph-1")),
    )

    with pytest.raises(RuntimeError, match="Graphiti local graph store is unreadable"):
        await graphiti_graph.get_graph_visualization("proj-1", db=AsyncMock())

    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_graph_removes_project_store(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(graphiti_graph.settings, "GRAPHITI_DB_PATH", str(tmp_path / "graphiti" / "graphiti.kuzu"))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(graph_id="graph-1")),
    )
    db_path = tmp_path / "graphiti" / "proj-1" / "graphiti.kuzu"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("stub")
    graphiti_graph._GRAPHITI_SETUP_COMPLETE.add(str(db_path))

    await graphiti_graph.delete_graph("proj-1", db=AsyncMock())

    assert not db_path.parent.exists()
    assert str(db_path) not in graphiti_graph._GRAPHITI_SETUP_COMPLETE


@pytest.mark.asyncio
async def test_delete_graph_accepts_legacy_runtime_kwargs(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(graphiti_graph.settings, "GRAPHITI_DB_PATH", str(tmp_path / "graphiti" / "graphiti.kuzu"))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(graph_id="graph-1")),
    )
    db_path = tmp_path / "graphiti" / "proj-legacy" / "graphiti.kuzu"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("stub")

    await graphiti_graph.delete_graph(
        "proj-legacy",
        model="chat-model",
        embedding_model="embed-model",
        db=AsyncMock(),
    )

    assert not db_path.parent.exists()


@pytest.mark.asyncio
async def test_setup_graphiti_initializes_kuzu_store(monkeypatch: pytest.MonkeyPatch, tmp_path):
    build_indices = AsyncMock()
    close = AsyncMock()
    driver_instances = []

    class FakeKuzuDriver:
        def __init__(self, *args, **kwargs):
            driver_instances.append(kwargs)
            self.execute_query = AsyncMock(return_value=([], None, None))

        async def build_indices_and_constraints(self):
            await build_indices()

        async def close(self):
            await close()

    monkeypatch.setattr(graphiti_graph.settings, "GRAPHITI_DB_PATH", str(tmp_path / "graphiti" / "graphiti.kuzu"))
    monkeypatch.setattr(
        graphiti_graph,
        "_import_graphiti_runtime",
        lambda: (object, FakeKuzuDriver, object, object, object, object, object, object, {}),
    )

    await graphiti_graph.setup_graphiti("proj-1")

    assert driver_instances[0]["db"].endswith("proj-1\\graphiti.kuzu") or driver_instances[0]["db"].endswith("proj-1/graphiti.kuzu")
    assert driver_instances
    assert driver_instances[0]["db"]
    close.assert_awaited_once()


@pytest.mark.asyncio
async def test_has_graph_data_returns_false_when_store_missing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(graphiti_graph.settings, "GRAPHITI_DB_PATH", str(tmp_path / "graphiti" / "graphiti.kuzu"))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(graph_id="graph-1")),
    )

    assert await graphiti_graph.has_graph_data("proj-missing", db=AsyncMock()) is False


@pytest.mark.asyncio
async def test_has_graph_data_checks_entity_count(monkeypatch: pytest.MonkeyPatch, tmp_path):
    close = AsyncMock()

    class FakeKuzuDriver:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def execute_query(self, *_args, **_kwargs):
            return ([{"node_count": 2}], None, None)

        async def close(self):
            await close()

    db_path = tmp_path / "graphiti" / "proj-1" / "graphiti.kuzu"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("stub")
    monkeypatch.setattr(graphiti_graph.settings, "GRAPHITI_DB_PATH", str(tmp_path / "graphiti" / "graphiti.kuzu"))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(graph_id="graph-1")),
    )
    monkeypatch.setattr(graphiti_graph, "setup_graphiti", AsyncMock())
    monkeypatch.setattr(
        graphiti_graph,
        "_import_graphiti_runtime",
        lambda: (object, FakeKuzuDriver, object, object, object, object, object, object, {}),
    )

    assert await graphiti_graph.has_graph_data("proj-1", db=AsyncMock()) is True
    close.assert_awaited_once()


from __future__ import annotations

import asyncio
import os
from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import cognee as cognee_service


@pytest.fixture(autouse=True)
def _force_cognee_backend(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cognee_service.settings, "GRAPH_BACKEND", "cognee", raising=False)
    yield


class _FakeSearchType(Enum):
    NATURAL_LANGUAGE = "nl"
    SUMMARIES = "sum"
    CHUNKS = "chunks"
    GRAPH_COMPLETION = "graph"
    RAG_COMPLETION = "rag"
    GRAPH_SUMMARY_COMPLETION = "graph_summary"
    INSIGHTS = "insights"


class TestCogneeHelpers:
    """Test cognee service helper functions."""

    def test_build_search_type_map_handles_missing_insights(self):
        type_map, default_type = cognee_service._build_search_type_map(_FakeSearchType)

        assert type_map["INSIGHTS"] == _FakeSearchType.INSIGHTS
        assert type_map["GRAPH_COMPLETION"] == _FakeSearchType.GRAPH_COMPLETION
        assert default_type == _FakeSearchType.GRAPH_COMPLETION

    def test_build_search_type_map_empty_enum(self):
        """Test _build_search_type_map with empty enum."""
        class EmptyEnum(Enum):
            pass

        type_map, default_type = cognee_service._build_search_type_map(EmptyEnum)
        assert type_map == {}
        assert default_type is None

    def test_build_search_type_map_finds_default(self):
        """Test _build_search_type_map finds appropriate default."""
        class MinimalEnum(Enum):
            NATURAL_LANGUAGE = "nl"
            CHUNKS = "chunks"

        type_map, default_type = cognee_service._build_search_type_map(MinimalEnum)
        assert default_type is not None

    def test_merge_alias_entities_for_cjk_names(self):
        """Test CJK alias names are merged and edges deduplicated."""
        nodes = [
            {"id": "n1", "type": "Entity", "name": "林黛玉", "label": "林黛玉"},
            {"id": "n2", "type": "Entity", "name": "黛玉", "label": "黛玉"},
            {"id": "n3", "type": "Entity", "name": "贾宝玉", "label": "贾宝玉"},
        ]
        edges = [
            {"source": "n1", "target": "n3", "label": "KNOWS"},
            {"source": "n2", "target": "n3", "label": "KNOWS"},
        ]

        merged_nodes, merged_edges = cognee_service._merge_alias_entities(nodes, edges)
        assert len(merged_nodes) == 2
        merged_main = next(node for node in merged_nodes if node["name"] == "林黛玉")
        assert "aliases" in merged_main
        assert "黛玉" in merged_main["aliases"]
        assert len(merged_edges) == 1

    def test_merge_alias_entities_skips_non_cjk(self):
        """Test non-CJK names are not merged by alias heuristic."""
        nodes = [
            {"id": "n1", "type": "Entity", "name": "Alice", "label": "Alice"},
            {"id": "n2", "type": "Entity", "name": "Alicia", "label": "Alicia"},
        ]
        merged_nodes, merged_edges = cognee_service._merge_alias_entities(nodes, [])
        assert len(merged_nodes) == 2
        assert merged_edges == []

    def test_merge_alias_entities_avoids_prefix_event_expansion(self):
        """Prefix-expanded phrases should not be treated as person aliases."""
        nodes = [
            {"id": "n1", "type": "Entity", "name": "璐炬瘝", "label": "璐炬瘝"},
            {"id": "n2", "type": "Entity", "name": "璐炬瘝鍘讳笘", "label": "璐炬瘝鍘讳笘"},
            {"id": "n3", "type": "Entity", "name": "璐炬瘝涓т簨", "label": "璐炬瘝涓т簨"},
            {"id": "n4", "type": "Entity", "name": "璐炬瘝瀵垮", "label": "璐炬瘝瀵垮"},
        ]

        merged_nodes, _ = cognee_service._merge_alias_entities(nodes, [])
        assert len(merged_nodes) == 4
        assert {node["name"] for node in merged_nodes} == {"璐炬瘝", "璐炬瘝鍘讳笘", "璐炬瘝涓т簨", "璐炬瘝瀵垮"}

    def test_merge_alias_entities_supports_llm_decision_override(self):
        """LLM decisions can explicitly force merge/non-merge for ambiguous pairs."""
        nodes = [
            {"id": "n1", "type": "Entity", "name": "璐炬瘝", "label": "璐炬瘝"},
            {"id": "n2", "type": "Entity", "name": "璐炬瘝澶悰", "label": "璐炬瘝澶悰"},
        ]
        pair_key = cognee_service._alias_pair_key("璐炬瘝", "璐炬瘝澶悰")
        merged_default, _ = cognee_service._merge_alias_entities(nodes, [])
        assert len(merged_default) == 2

        merged_forced, _ = cognee_service._merge_alias_entities(
            nodes,
            [],
            alias_decisions={pair_key: True},
        )
        assert len(merged_forced) == 1

        merged_blocked, _ = cognee_service._merge_alias_entities(
            nodes,
            [],
            alias_decisions={pair_key: False},
        )
        assert len(merged_blocked) == 2


    @pytest.mark.asyncio
    async def test_resolve_alias_merge_decisions_with_llm_parses_json(self, monkeypatch: pytest.MonkeyPatch):
        nodes = [
            {"id": "n1", "type": "Entity", "name": "\u6797\u9edb\u7389", "label": "\u6797\u9edb\u7389"},
            {"id": "n2", "type": "Entity", "name": "\u9edb\u7389", "label": "\u9edb\u7389"},
            {"id": "n3", "type": "Entity", "name": "\u8d3e\u6bcd", "label": "\u8d3e\u6bcd"},
            {"id": "n4", "type": "Entity", "name": "\u8d3e\u6bcd\u53bb\u4e16", "label": "\u8d3e\u6bcd\u53bb\u4e16"},
        ]
        llm_mock = AsyncMock(
            return_value={
                "content": (
                    '{"decisions": ['
                    '{"left":"\\u6797\\u9edb\\u7389","right":"\\u9edb\\u7389","same_entity":true},'
                    '{"left":"\\u8d3e\\u6bcd","right":"\\u8d3e\\u6bcd\\u53bb\\u4e16","same_entity":false}'
                    ']}'
                )
            }
        )
        cognee_service._ALIAS_DECISION_CACHE.clear()
        monkeypatch.setitem(cognee_service.__dict__, "call_llm", llm_mock)

        decisions = await cognee_service._resolve_alias_merge_decisions_with_llm(
            nodes,
            db=AsyncMock(),
            model="gpt-4o-mini",
        )

        assert decisions[cognee_service._alias_pair_key("\u6797\u9edb\u7389", "\u9edb\u7389")] is True
        assert decisions[cognee_service._alias_pair_key("\u8d3e\u6bcd", "\u8d3e\u6bcd\u53bb\u4e16")] is False
        llm_mock.assert_awaited_once()


class TestCogneeRuntimeConfigHelpers:
    def test_apply_cognee_embedding_config_sets_runtime_env(self, monkeypatch: pytest.MonkeyPatch):
        for key in ("EMBEDDING_MODEL", "EMBEDDING_PROVIDER", "EMBEDDING_API_KEY", "EMBEDDING_ENDPOINT"):
            monkeypatch.delenv(key, raising=False)

        cognee_service._apply_cognee_embedding_config(
            config_obj=None,
            model="text-embedding-3-small",
            api_key="embed-key",
            endpoint="https://api.example.com/v1",
            provider="openai_compatible",
        )

        assert os.environ["EMBEDDING_MODEL"] == "openai/text-embedding-3-small"
        assert os.environ["EMBEDDING_PROVIDER"] == "openai"
        assert os.environ["EMBEDDING_API_KEY"] == "embed-key"
        assert os.environ["EMBEDDING_ENDPOINT"] == "https://api.example.com/v1"

    def test_resolve_cognee_runtime_provider_uses_openai_for_openai_compatible_gateway(self):
        assert cognee_service._resolve_cognee_runtime_provider(
            "openai_compatible",
            endpoint="https://api.example.com/v1",
            purpose="llm",
        ) == "openai"

    def test_resolve_cognee_runtime_provider_rejects_anthropic_embedding(self):
        with pytest.raises(RuntimeError, match="does not support anthropic-compatible providers"):
            cognee_service._resolve_cognee_runtime_provider(
                "anthropic_compatible",
                endpoint=None,
                purpose="embedding",
            )

    def test_clear_cognee_runtime_caches_calls_cache_clear(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[str] = []

        class _CacheTarget:
            def cache_clear(self):
                calls.append("cleared")

        class _FakeModule:
            get_fake_cache = _CacheTarget()

        monkeypatch.setattr(
            cognee_service,
            "_COGNEE_RUNTIME_CACHE_TARGETS",
            (("tests.fake_cognee_cache", "get_fake_cache"),),
        )

        import sys

        monkeypatch.setitem(sys.modules, "tests.fake_cognee_cache", _FakeModule())

        cognee_service._clear_cognee_runtime_caches()

        assert calls == ["cleared"]


    @pytest.mark.asyncio
    async def test_prepare_cognee_search_runtime_uses_project_models(self, monkeypatch: pytest.MonkeyPatch):
        project = SimpleNamespace(id="p1")
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = project
        db.execute.return_value = result
        configure_mock = AsyncMock()

        monkeypatch.setitem(cognee_service.__dict__, "_configure_cognee_llm", configure_mock)
        monkeypatch.setitem(
            cognee_service.__dict__,
            "resolve_component_model",
            lambda project_obj, component: {
                "graph_build": "chat-model",
                "graph_embedding": "embed-model",
            }[component],
        )

        await cognee_service.prepare_cognee_search_runtime("p1", db)

        configure_mock.assert_awaited_once_with(
            model="chat-model",
            embedding_model="embed-model",
            db=db,
        )


class TestSearchGraph:
    """Test search_graph function."""

    @pytest.mark.asyncio
    async def test_search_graph_falls_back_to_default_type(self, monkeypatch: pytest.MonkeyPatch):
        fake_search = AsyncMock(return_value=[{"content": "ok"}])
        monkeypatch.setitem(cognee_service.__dict__, "_SEARCH_TYPE_MAP", {"GRAPH_COMPLETION": _FakeSearchType.GRAPH_COMPLETION})
        monkeypatch.setitem(cognee_service.__dict__, "_DEFAULT_SEARCH_TYPE", _FakeSearchType.GRAPH_COMPLETION)
        monkeypatch.setitem(cognee_service.__dict__, "_get_search_type_map", lambda: {"GRAPH_COMPLETION": _FakeSearchType.GRAPH_COMPLETION})
        monkeypatch.setitem(cognee_service.__dict__, "cognee", SimpleNamespace(search=fake_search))

        class _CogneeModule:
            search = fake_search

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        results = await cognee_service.search_graph(
            project_id="p1",
            query="q",
            search_type="INSIGHTS",
            top_k=3,
        )

        assert results == [{"content": "ok", "score": 1.0}]
        fake_search.assert_awaited_once()
        kwargs = fake_search.await_args.kwargs
        assert kwargs["query_type"] == _FakeSearchType.GRAPH_COMPLETION
        assert kwargs["top_k"] == 3
        assert kwargs["datasets"] == ["project-p1"]

    @pytest.mark.asyncio
    async def test_search_graph_prepares_runtime_when_db_provided(self, monkeypatch: pytest.MonkeyPatch):
        fake_search = AsyncMock(return_value=[{"content": "ok"}])
        prepare_mock = AsyncMock()
        db = AsyncMock()

        monkeypatch.setitem(
            cognee_service.__dict__,
            "_get_search_type_map",
            lambda: {"INSIGHTS": _FakeSearchType.INSIGHTS},
        )
        monkeypatch.setitem(cognee_service.__dict__, "_DEFAULT_SEARCH_TYPE", _FakeSearchType.INSIGHTS)
        monkeypatch.setitem(cognee_service.__dict__, "prepare_cognee_search_runtime", prepare_mock)

        class _CogneeModule:
            search = fake_search

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        await cognee_service.search_graph(
            project_id="p1",
            query="q",
            search_type="INSIGHTS",
            top_k=2,
            db=db,
        )

        assert prepare_mock.await_count >= 1
        assert prepare_mock.await_args_list[0].args == ("p1", db)
        fake_search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_graph_raises_when_all_candidates_fail(self, monkeypatch: pytest.MonkeyPatch):
        async def _search(**_kwargs):
            raise RuntimeError("search failed")

        monkeypatch.setitem(
            cognee_service.__dict__,
            "_get_search_type_map",
            lambda: {"GRAPH_COMPLETION": _FakeSearchType.GRAPH_COMPLETION},
        )
        monkeypatch.setitem(cognee_service.__dict__, "_DEFAULT_SEARCH_TYPE", _FakeSearchType.GRAPH_COMPLETION)

        class _CogneeModule:
            search = staticmethod(_search)

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        with pytest.raises(RuntimeError, match="Cognee search failed for dataset project-p1"):
            await cognee_service.search_graph(
                project_id="p1",
                query="q",
                search_type="GRAPH_COMPLETION",
                top_k=3,
            )

    @pytest.mark.asyncio
    async def test_search_graph_uses_lexical_reranker_when_enabled(self, monkeypatch: pytest.MonkeyPatch):
        async def _search(**_kwargs):
            return [
                {"content": "\u8d3e\u6bcd\u53c2\u52a0\u5bb4\u4f1a"},
                {"content": "\u6797\u9edb\u7389\u5728\u5927\u89c2\u56ed\u629a\u7434"},
            ]

        monkeypatch.setitem(
            cognee_service.__dict__,
            "_get_search_type_map",
            lambda: {"INSIGHTS": _FakeSearchType.INSIGHTS},
        )
        monkeypatch.setitem(cognee_service.__dict__, "_DEFAULT_SEARCH_TYPE", _FakeSearchType.INSIGHTS)
        monkeypatch.setitem(cognee_service.__dict__, "prepare_cognee_search_runtime", AsyncMock())

        class _CogneeModule:
            search = staticmethod(_search)

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        results = await cognee_service.search_graph(
            project_id="p1",
            query="\u6797\u9edb\u7389",
            search_type="INSIGHTS",
            top_k=2,
            use_reranker=True,
            reranker_top_n=1,
        )

        assert len(results) == 1
        assert "\u6797\u9edb\u7389" in str(results[0].get("content") or "")
        assert results[0].get("reranker_source") == "lexical_fallback"

    @pytest.mark.asyncio
    async def test_search_graph_uses_llm_reranker_when_model_provided(self, monkeypatch: pytest.MonkeyPatch):
        async def _search(**_kwargs):
            return [
                {"content": "A result about weather"},
                {"content": "B result about treasure map"},
            ]

        llm_mock = AsyncMock(
            return_value={
                "content": '{"ranked":[{"id":2,"score":0.99},{"id":1,"score":0.10}]}'
            }
        )
        prepare_mock = AsyncMock()
        monkeypatch.setitem(cognee_service.__dict__, "call_llm", llm_mock)
        monkeypatch.setitem(cognee_service.__dict__, "prepare_cognee_search_runtime", prepare_mock)
        monkeypatch.setitem(
            cognee_service.__dict__,
            "_get_search_type_map",
            lambda: {"INSIGHTS": _FakeSearchType.INSIGHTS},
        )
        monkeypatch.setitem(cognee_service.__dict__, "_DEFAULT_SEARCH_TYPE", _FakeSearchType.INSIGHTS)

        class _CogneeModule:
            search = staticmethod(_search)

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        results = await cognee_service.search_graph(
            project_id="p1",
            query="treasure",
            search_type="INSIGHTS",
            top_k=2,
            db=AsyncMock(),
            use_reranker=True,
            reranker_model="gpt-4o-mini",
            reranker_top_n=2,
        )

        assert len(results) == 2
        assert str(results[0].get("content") or "").startswith("B result")
        assert results[0].get("reranker_source") == "llm"
        llm_mock.assert_awaited_once()


class TestAddAndCognify:
    """Test add_and_cognify function."""

    @pytest.mark.asyncio
    async def test_add_and_cognify_raises_when_cognify_fails(self, monkeypatch: pytest.MonkeyPatch):
        add_mock = AsyncMock()
        cognify_mock = AsyncMock(side_effect=RuntimeError("cognify failed"))
        memify_mock = AsyncMock()

        class _CogneeModule:
            add = add_mock
            cognify = cognify_mock
            memify = memify_mock

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        with pytest.raises(RuntimeError, match="cognify failed"):
            await cognee_service.add_and_cognify("p1", "text")
        add_mock.assert_awaited_once()
        cognify_kwargs = cognify_mock.await_args.kwargs
        assert cognify_kwargs["datasets"] == ["project-p1"]
        schema = cognify_kwargs["graph_model"].model_json_schema()
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"nodes", "edges"}
        memify_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_and_cognify_success(self, monkeypatch: pytest.MonkeyPatch):
        """Test successful add_and_cognify."""
        add_mock = AsyncMock()
        cognify_mock = AsyncMock()
        memify_mock = AsyncMock()

        class _CogneeModule:
            add = add_mock
            cognify = cognify_mock
            memify = memify_mock

        import sys
        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        dataset = await cognee_service.add_and_cognify("p1", "test content")

        assert dataset == "project-p1"
        add_mock.assert_awaited_once_with("test content", dataset_name="project-p1")
        cognify_kwargs = cognify_mock.await_args.kwargs
        assert cognify_kwargs["datasets"] == ["project-p1"]
        schema = cognify_kwargs["graph_model"].model_json_schema()
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"nodes", "edges"}
        memify_mock.assert_awaited_once_with(dataset="project-p1")

    def test_strict_cognee_summary_schema_is_provider_compatible(self):
        schema = cognee_service._StrictCogneeSummarizedContent.model_json_schema()

        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"summary", "description"}

    @pytest.mark.asyncio
    async def test_add_and_cognify_rewrites_structured_schema_errors(self, monkeypatch: pytest.MonkeyPatch):
        add_mock = AsyncMock()
        cognify_mock = AsyncMock(
            side_effect=RuntimeError(
                "Invalid schema for response_format 'KnowledgeGraph': In context=(), 'additionalProperties' is required to be supplied and to be false."
            )
        )
        memify_mock = AsyncMock()

        class _CogneeModule:
            add = add_mock
            cognify = cognify_mock
            memify = memify_mock

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        with pytest.raises(RuntimeError, match="provider rejected Cognee structured JSON schema"):
            await cognee_service.add_and_cognify("p1", "text")
        memify_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_and_cognify_rewrites_provider_timeout_errors(self, monkeypatch: pytest.MonkeyPatch):
        add_mock = AsyncMock()
        cognify_mock = AsyncMock(
            side_effect=RuntimeError(
                "Timeout Error: OpenAIException - <!DOCTYPE html><title>504: Gateway time-out</title>"
            )
        )
        memify_mock = AsyncMock()

        class _CogneeModule:
            add = add_mock
            cognify = cognify_mock
            memify = memify_mock

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        with pytest.raises(RuntimeError, match="upstream model gateway timed out"):
            await cognee_service.add_and_cognify("p1", "text")
        memify_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_and_cognify_caps_graph_runtime_overrides(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MUSEGRAPH_LLM_REQUEST_TIMEOUT_SECONDS", "180")
        monkeypatch.setenv("MUSEGRAPH_LLM_RETRY_COUNT", "4")
        monkeypatch.setenv("MUSEGRAPH_GRAPH_BUILD_HEARTBEAT_SECONDS", "0")
        monkeypatch.setattr(cognee_service, "_configure_cognee_llm", AsyncMock())

        observed: dict[str, int] = {}

        async def _fake_cognify(**_kwargs):
            observed["timeout"] = cognee_service._runtime_litellm_timeout_seconds()
            observed["retry_count"] = cognee_service._runtime_litellm_retry_count()

        add_mock = AsyncMock()
        memify_mock = AsyncMock()

        class _CogneeModule:
            add = add_mock
            cognify = staticmethod(_fake_cognify)
            memify = memify_mock

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        dataset = await cognee_service.add_and_cognify("p1", "text")

        assert dataset == "project-p1"
        assert observed == {"timeout": 120, "retry_count": 1}
        assert cognee_service._runtime_litellm_timeout_seconds() == 180
        assert cognee_service._runtime_litellm_retry_count() == 4

    @pytest.mark.asyncio
    async def test_add_and_cognify_emits_heartbeat_for_long_cognify(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MUSEGRAPH_GRAPH_BUILD_HEARTBEAT_SECONDS", "0.01")
        monkeypatch.setenv("MUSEGRAPH_LLM_RETRY_COUNT", "0")
        monkeypatch.setattr(cognee_service, "_configure_cognee_llm", AsyncMock())

        events: list[tuple[int, str]] = []

        async def _fake_cognify(**_kwargs):
            await asyncio.sleep(0.03)

        add_mock = AsyncMock()
        memify_mock = AsyncMock()

        class _CogneeModule:
            add = add_mock
            cognify = staticmethod(_fake_cognify)
            memify = memify_mock

        import sys

        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        await cognee_service.add_and_cognify(
            "p1",
            "text",
            progress_callback=lambda progress, message: events.append((progress, message)),
        )

        assert any("waiting for provider responses" in message.lower() for _, message in events)



class TestGetGraphVisualization:
    """Test get_graph_visualization function."""

    @pytest.mark.asyncio
    async def test_get_graph_visualization_empty(self, monkeypatch: pytest.MonkeyPatch):
        """Test visualization with no data."""
        datasets_mock = AsyncMock(return_value=[])
        get_data_mock = AsyncMock(return_value=[])
        get_user_mock = AsyncMock(return_value=SimpleNamespace(id="u1"))
        get_engine_mock = AsyncMock()

        import sys
        monkeypatch.setitem(
            sys.modules,
            "cognee.modules.users.methods",
            SimpleNamespace(get_default_user=get_user_mock),
        )
        monkeypatch.setitem(
            sys.modules,
            "cognee.modules.data.methods",
            SimpleNamespace(
                get_authorized_existing_datasets=datasets_mock,
                get_dataset_data=get_data_mock,
            ),
        )
        monkeypatch.setitem(
            sys.modules,
            "cognee.infrastructure.databases.graph",
            SimpleNamespace(get_graph_engine=get_engine_mock),
        )

        result = await cognee_service.get_graph_visualization("p1")
        assert result == {"nodes": [], "edges": []}

    @pytest.mark.asyncio
    async def test_get_graph_visualization_builds_dataset_subgraph(self, monkeypatch: pytest.MonkeyPatch):
        get_user_mock = AsyncMock(return_value=SimpleNamespace(id="u1"))
        datasets_mock = AsyncMock(return_value=[SimpleNamespace(id="d1", name="project-p1")])
        get_data_mock = AsyncMock(return_value=[SimpleNamespace(id="doc-1")])

        fake_engine = SimpleNamespace(
            get_id_filtered_graph_data=AsyncMock(
                side_effect=[
                    (
                        [
                            ("doc-1", {"id": "doc-1", "name": "Doc", "type": "TextDocument"}),
                            ("chunk-1", {"id": "chunk-1", "text": "chunk text", "type": "DocumentChunk"}),
                        ],
                        [("chunk-1", "doc-1", "is_part_of", {"relationship_name": "is_part_of"})],
                    ),
                    (
                        [
                            ("chunk-1", {"id": "chunk-1", "text": "chunk text", "type": "DocumentChunk"}),
                            ("ent-1", {"id": "ent-1", "name": "Entity A", "type": "Entity"}),
                        ],
                        [("chunk-1", "ent-1", "contains", {"relationship_name": "contains"})],
                    ),
                    (
                        [("ent-1", {"id": "ent-1", "name": "Entity A", "type": "Entity"})],
                        [],
                    ),
                ]
            )
        )
        get_engine_mock = AsyncMock(return_value=fake_engine)

        import sys
        monkeypatch.setitem(
            sys.modules,
            "cognee.modules.users.methods",
            SimpleNamespace(get_default_user=get_user_mock),
        )
        monkeypatch.setitem(
            sys.modules,
            "cognee.modules.data.methods",
            SimpleNamespace(
                get_authorized_existing_datasets=datasets_mock,
                get_dataset_data=get_data_mock,
            ),
        )
        monkeypatch.setitem(
            sys.modules,
            "cognee.infrastructure.databases.graph",
            SimpleNamespace(get_graph_engine=get_engine_mock),
        )

        result = await cognee_service.get_graph_visualization("p1")
        assert len(result["nodes"]) >= 2
        assert any(item["label"] == "Entity A" for item in result["nodes"])
        assert any(item["label"] == "contains" for item in result["edges"])

    @pytest.mark.asyncio
    async def test_get_graph_visualization_keeps_structural_preview_when_semantic_not_ready(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        get_user_mock = AsyncMock(return_value=SimpleNamespace(id="u1"))
        datasets_mock = AsyncMock(return_value=[SimpleNamespace(id="d1", name="project-p1")])
        get_data_mock = AsyncMock(return_value=[SimpleNamespace(id="doc-1")])

        fake_engine = SimpleNamespace(
            get_id_filtered_graph_data=AsyncMock(
                side_effect=[
                    (
                        [
                            ("doc-1", {"id": "doc-1", "name": "Doc", "type": "TextDocument"}),
                            ("chunk-1", {"id": "chunk-1", "text": "chunk text", "type": "DocumentChunk"}),
                        ],
                        [("chunk-1", "doc-1", "is_part_of", {"relationship_name": "is_part_of"})],
                    ),
                    ([], []),
                    ([], []),
                ]
            )
        )
        get_engine_mock = AsyncMock(return_value=fake_engine)

        import sys
        monkeypatch.setitem(
            sys.modules,
            "cognee.modules.users.methods",
            SimpleNamespace(get_default_user=get_user_mock),
        )
        monkeypatch.setitem(
            sys.modules,
            "cognee.modules.data.methods",
            SimpleNamespace(
                get_authorized_existing_datasets=datasets_mock,
                get_dataset_data=get_data_mock,
            ),
        )
        monkeypatch.setitem(
            sys.modules,
            "cognee.infrastructure.databases.graph",
            SimpleNamespace(get_graph_engine=get_engine_mock),
        )

        result = await cognee_service.get_graph_visualization("p1")
        assert len(result["nodes"]) >= 1
        assert any(item["label"] == "Doc" for item in result["nodes"])


class TestDeleteDataset:
    """Test delete_dataset function."""

    @pytest.mark.asyncio
    async def test_delete_dataset_graphiti_branch_ignores_runtime_model_kwargs(self, monkeypatch: pytest.MonkeyPatch):
        delete_mock = AsyncMock()
        monkeypatch.setitem(cognee_service.__dict__, "_use_graphiti_graph_backend", lambda: True)

        import sys
        monkeypatch.setitem(
            sys.modules,
            "app.services.graphiti_graph",
            SimpleNamespace(delete_graph=delete_mock),
        )

        db = AsyncMock()
        await cognee_service.delete_dataset(
            "p1",
            model="chat-model",
            embedding_model="embed-model",
            db=db,
        )

        delete_mock.assert_awaited_once_with("p1", db=db)

    @pytest.mark.asyncio
    async def test_delete_dataset_uses_empty_dataset_when_available(self, monkeypatch: pytest.MonkeyPatch):
        list_datasets_mock = AsyncMock(
            return_value=[
                SimpleNamespace(id="dataset-1", name="project-p1"),
                SimpleNamespace(id="dataset-2", name="project-p2"),
            ]
        )
        empty_dataset_mock = AsyncMock()

        class _DatasetsModule:
            list_datasets = list_datasets_mock
            empty_dataset = empty_dataset_mock

        class _CogneeModule:
            datasets = _DatasetsModule()

        import sys
        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        await cognee_service.delete_dataset("p1")
        list_datasets_mock.assert_awaited_once_with()
        empty_dataset_mock.assert_awaited_once_with("dataset-1")

    @pytest.mark.asyncio
    async def test_delete_dataset_noop_when_dataset_missing(self, monkeypatch: pytest.MonkeyPatch):
        list_datasets_mock = AsyncMock(
            return_value=[SimpleNamespace(id="dataset-2", name="project-p2")]
        )
        empty_dataset_mock = AsyncMock()

        class _DatasetsModule:
            list_datasets = list_datasets_mock
            empty_dataset = empty_dataset_mock

        class _CogneeModule:
            datasets = _DatasetsModule()

        import sys
        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        await cognee_service.delete_dataset("p1")
        list_datasets_mock.assert_awaited_once_with()
        empty_dataset_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_dataset_raises_when_datasets_api_missing(self, monkeypatch: pytest.MonkeyPatch):
        class _CogneeModule:
            datasets = object()

        import sys
        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        with pytest.raises(RuntimeError, match="Cognee datasets API unavailable"):
            await cognee_service.delete_dataset("p1")

    @pytest.mark.asyncio
    async def test_delete_dataset_propagates_delete_errors(self, monkeypatch: pytest.MonkeyPatch):
        list_datasets_mock = AsyncMock(return_value=[SimpleNamespace(id="dataset-1", name="project-p1")])
        empty_dataset_mock = AsyncMock(side_effect=RuntimeError("delete failed"))

        class _DatasetsModule:
            list_datasets = list_datasets_mock
            empty_dataset = empty_dataset_mock

        class _CogneeModule:
            datasets = _DatasetsModule()

        import sys
        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())

        with pytest.raises(RuntimeError):
            await cognee_service.delete_dataset("p1")

    @pytest.mark.asyncio
    async def test_delete_dataset_fallbacks_on_sqlite_expression_tree_error(self, monkeypatch: pytest.MonkeyPatch):
        dataset = SimpleNamespace(id="dataset-1", name="project-p1")
        list_datasets_mock = AsyncMock(return_value=[dataset])
        empty_dataset_mock = AsyncMock(
            side_effect=RuntimeError(
                "sqlite3.OperationalError: Expression tree is too large (maximum depth 1000)"
            )
        )
        delete_dataset_record_mock = AsyncMock()

        class _DatasetsModule:
            list_datasets = list_datasets_mock
            empty_dataset = empty_dataset_mock

        class _CogneeModule:
            datasets = _DatasetsModule()

        import sys
        monkeypatch.setitem(sys.modules, "cognee", _CogneeModule())
        monkeypatch.setitem(
            sys.modules,
            "cognee.modules.data.methods",
            SimpleNamespace(delete_dataset=delete_dataset_record_mock),
        )

        await cognee_service.delete_dataset("p1")
        empty_dataset_mock.assert_awaited_once_with("dataset-1")
        delete_dataset_record_mock.assert_awaited_once_with(dataset)

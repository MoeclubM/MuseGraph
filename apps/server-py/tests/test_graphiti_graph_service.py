from __future__ import annotations

from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.services import graphiti_graph


@pytest.fixture(autouse=True)
def _reset_graphiti_setup_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(graphiti_graph, "_GRAPHITI_SETUP_COMPLETE", set())
    yield


def _fake_import_runtime():
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

    recipes = {
        "combined_rrf": SimpleNamespace(model_copy=lambda deep=True: SimpleNamespace(limit=10)),
        "edge_rrf": SimpleNamespace(model_copy=lambda deep=True: SimpleNamespace(limit=10)),
        "node_rrf": SimpleNamespace(model_copy=lambda deep=True: SimpleNamespace(limit=10)),
    }
    return object, KuzuDriver, object, object, object, object, object, EpisodeType, recipes


def _runtime_selection() -> graphiti_graph._GraphitiRuntimeSelection:
    return graphiti_graph._GraphitiRuntimeSelection(
        llm_model="chat-model",
        llm_api_key="llm-key",
        llm_base_url="https://example.com/v1",
        embedding_model="embed-model",
        embedding_api_key="embed-key",
        embedding_base_url="https://example.com/v1",
        reranker_model="chat-model",
        timeout_seconds=120,
        retry_count=1,
        max_coroutines=2,
    )


def test_patch_graphiti_driver_compatibility_sets_database_and_clone():
    driver = SimpleNamespace()
    patched = graphiti_graph._patch_graphiti_driver_compatibility(driver)

    assert patched._database == ""
    assert patched.clone(database="graph-1") is patched
    assert patched._database == "graph-1"


@pytest.mark.asyncio
async def test_patch_graphiti_driver_compatibility_builds_kuzu_fulltext_indices():
    driver = SimpleNamespace(execute_query=AsyncMock())
    patched = graphiti_graph._patch_graphiti_driver_compatibility(driver)

    await patched.build_indices_and_constraints()

    created_queries = [call.args[0] for call in driver.execute_query.await_args_list]
    assert any("node_name_and_summary" in query for query in created_queries)
    assert any("episode_content" in query for query in created_queries)


def test_normalize_graphiti_structured_payload_maps_nodes_to_extracted_entities():
    ExtractedEntitiesModel = type("ExtractedEntities", (), {})

    payload = {"nodes": [{"name": "Alice", "entity_type_id": 1}]}

    normalized = graphiti_graph._normalize_graphiti_structured_payload(ExtractedEntitiesModel, payload)

    assert normalized == {"extracted_entities": [{"name": "Alice", "entity_type_id": 1}]}


def test_normalize_graphiti_structured_payload_wraps_single_field_list():
    class EntityList(BaseModel):
        extracted_entities: list[dict]

    normalized = graphiti_graph._normalize_graphiti_structured_payload(
        EntityList,
        [{"name": "Alice", "entity_type_id": 1}],
    )

    assert normalized == {"extracted_entities": [{"name": "Alice", "entity_type_id": 1}]}


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

    assert parsed == {"extracted_entities": [{"name": "Alice", "entity_type_id": 1}]}


def test_parse_graphiti_response_content_maps_entity_name_alias():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    raw = '{"extracted_entities":[{"entity_name":"Elena Varga","entity_type_id":1}]}'

    parsed = graphiti_graph._parse_graphiti_response_content(ExtractedEntities, raw)

    assert parsed == {"extracted_entities": [{"name": "Elena Varga", "entity_type_id": 1}]}


def test_parse_graphiti_response_content_preserves_top_level_list():
    class ExtractedEntities(BaseModel):
        extracted_entities: list[dict]

    raw = '[{"entity_name":"Elena Varga","entity_type_id":1}]'

    parsed = graphiti_graph._parse_graphiti_response_content(ExtractedEntities, raw)

    assert parsed == {"extracted_entities": [{"name": "Elena Varga", "entity_type_id": 1}]}


def test_parse_graphiti_response_content_wraps_plain_text_single_field():
    class Summary(BaseModel):
        summary: str

    parsed = graphiti_graph._parse_graphiti_response_content(
        Summary,
        "Alice leads the core investigation.",
    )

    assert parsed == {"summary": "Alice leads the core investigation."}


def test_normalize_graphiti_structured_payload_wraps_single_item_for_list_field():
    class NodeResolutions(BaseModel):
        entity_resolutions: list[dict]

    normalized = graphiti_graph._normalize_graphiti_structured_payload(
        NodeResolutions,
        {"id": 0, "entity_name": "Mira", "duplicate_name": ""},
    )

    assert normalized == {"entity_resolutions": [{"id": 0, "name": "Mira", "duplicate_name": ""}]}


def test_normalize_graphiti_structured_payload_synthesizes_edge_fact():
    ExtractedEdgesModel = type("ExtractedEdges", (), {})

    payload = {
        "relationships": [
            {
                "source": "Alice",
                "target": "Bob",
                "relation": "KNOWS",
            }
        ]
    }

    normalized = graphiti_graph._normalize_graphiti_structured_payload(ExtractedEdgesModel, payload)

    assert normalized == {
        "edges": [
            {
                "source_entity_name": "Alice",
                "target_entity_name": "Bob",
                "relation_type": "KNOWS",
                "fact": "Alice knows Bob",
            }
        ]
    }


def test_normalize_graphiti_structured_payload_maps_summary_dict_to_list():
    class SummarizedEntities(BaseModel):
        summaries: list[dict]

    normalized = graphiti_graph._normalize_graphiti_structured_payload(
        SummarizedEntities,
        {
            "Transit Plaza": "Transit hub where the breakdown became visible.",
            "Maya Chen": "Commuter caught in the disruption.",
        },
    )

    assert normalized == {
        "summaries": [
            {"name": "Transit Plaza", "summary": "Transit hub where the breakdown became visible."},
            {"name": "Maya Chen", "summary": "Commuter caught in the disruption."},
        ]
    }


def test_normalize_graphiti_structured_payload_maps_summary_string_lines_to_list():
    class SummarizedEntities(BaseModel):
        summaries: list[dict]

    normalized = graphiti_graph._normalize_graphiti_structured_payload(
        SummarizedEntities,
        {
            "summaries": '**Union Leadership**: "Transit workers demand better staffing."\n'
            '**City Operations**: "Officials are reviewing response gaps."'
        },
    )

    assert normalized == {
        "summaries": [
            {"name": "Union Leadership", "summary": "Transit workers demand better staffing."},
            {"name": "City Operations", "summary": "Officials are reviewing response gaps."},
        ]
    }


def test_normalize_graphiti_structured_payload_drops_unparseable_summary_string():
    class SummarizedEntities(BaseModel):
        summaries: list[dict]

    normalized = graphiti_graph._normalize_graphiti_structured_payload(
        SummarizedEntities,
        {"summaries": "A broad narrative summary with no entity headings."},
    )

    assert normalized == {"summaries": []}


def test_normalize_graphiti_structured_payload_defaults_missing_edge_duplicate_lists():
    class EdgeDuplicate(BaseModel):
        duplicate_facts: list[int]
        contradicted_facts: list[int]

    normalized = graphiti_graph._normalize_graphiti_structured_payload(
        EdgeDuplicate,
        {"idx": 0, "fact": "Marcus supports the Digital Commuters Alliance"},
    )

    assert normalized == {"duplicate_facts": [], "contradicted_facts": []}


def test_normalize_graphiti_structured_payload_maps_edge_duplicate_aliases():
    class EdgeDuplicate(BaseModel):
        duplicate_facts: list[int]
        contradicted_facts: list[int]

    normalized = graphiti_graph._normalize_graphiti_structured_payload(
        EdgeDuplicate,
        {"duplicates": ["1", 2.0], "contradictions": [3, "4"]},
    )

    assert normalized == {"duplicate_facts": [1, 2], "contradicted_facts": [3, 4]}


@pytest.mark.asyncio
async def test_build_graph_uses_existing_graph_id_and_adds_episodes(monkeypatch: pytest.MonkeyPatch):
    add_episode = AsyncMock(
        side_effect=[
            SimpleNamespace(episode=SimpleNamespace(uuid="ep-1")),
            SimpleNamespace(episode=SimpleNamespace(uuid="ep-2")),
        ]
    )
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
        AsyncMock(return_value=SimpleNamespace(title="Demo", cognee_dataset_id="graph-existing")),
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
        AsyncMock(return_value=SimpleNamespace(cognee_dataset_id="graph-1")),
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
        AsyncMock(return_value=SimpleNamespace(cognee_dataset_id="graph-1")),
    )

    payload = await graphiti_graph.get_graph_visualization("proj-1", db=AsyncMock())

    assert payload["nodes"][0]["label"] == "Alice"
    assert payload["nodes"][0]["attributes"] == {"role": "lead"}
    assert payload["edges"][0]["source_label"] == "Alice"
    assert payload["edges"][0]["attributes"] == {"confidence": "high"}
    fake_graphiti.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_graph_removes_project_store(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(graphiti_graph.settings, "GRAPHITI_DB_PATH", str(tmp_path / "graphiti" / "graphiti.kuzu"))
    monkeypatch.setattr(
        graphiti_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(cognee_dataset_id="graph-1")),
    )
    db_path = tmp_path / "graphiti" / "proj-1" / "graphiti.kuzu"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("stub")
    graphiti_graph._GRAPHITI_SETUP_COMPLETE.add(str(db_path))

    await graphiti_graph.delete_graph("proj-1", db=AsyncMock())

    assert not db_path.parent.exists()
    assert str(db_path) not in graphiti_graph._GRAPHITI_SETUP_COMPLETE


@pytest.mark.asyncio
async def test_setup_graphiti_initializes_kuzu_store(monkeypatch: pytest.MonkeyPatch, tmp_path):
    build_indices = AsyncMock()
    close = AsyncMock()
    driver_instances = []

    class FakeKuzuDriver:
        def __init__(self, *args, **kwargs):
            driver_instances.append(kwargs)

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
    build_indices.assert_awaited_once()
    close.assert_awaited_once()

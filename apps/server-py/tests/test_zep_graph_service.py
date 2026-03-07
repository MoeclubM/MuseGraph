from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import zep_graph


@pytest.fixture(autouse=True)
def _configure_zep_backend(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(zep_graph.settings, "ZEP_API_KEY", "zep-test-key", raising=False)
    yield


def _fake_import_runtime():
    class EpisodeData:
        def __init__(self, data: str, type: str):
            self.data = data
            self.type = type

    class EntityEdgeSourceTarget:
        def __init__(self, source: str, target: str):
            self.source = source
            self.target = target

    class EdgeModel:
        pass

    class EntityModel:
        pass

    EntityText = str

    def Field(**kwargs):
        return kwargs

    return object, EpisodeData, EntityEdgeSourceTarget, EdgeModel, EntityModel, EntityText, Field


@pytest.mark.asyncio
async def test_build_graph_creates_graph_and_waits(monkeypatch: pytest.MonkeyPatch):
    create_mock = MagicMock()
    set_ontology_mock = MagicMock()
    add_batch_mock = MagicMock(
        return_value=[SimpleNamespace(uuid_="ep-1"), SimpleNamespace(uuid_="ep-2")]
    )
    episode_get_mock = MagicMock(return_value=SimpleNamespace(processed=True))

    fake_client = SimpleNamespace(
        graph=SimpleNamespace(
            create=create_mock,
            set_ontology=set_ontology_mock,
            add_batch=add_batch_mock,
            episode=SimpleNamespace(get=episode_get_mock),
        )
    )

    monkeypatch.setattr(zep_graph, "_create_zep_client", lambda: fake_client)
    monkeypatch.setattr(zep_graph, "_import_zep_runtime", _fake_import_runtime)
    monkeypatch.setattr(
        zep_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", cognee_dataset_id=None)),
    )

    events: list[str] = []
    graph_id = await zep_graph.build_graph(
        "proj-1",
        "A" * 1200,
        ontology={
            "entity_types": [{"name": "Character", "attributes": [{"name": "role"}]}],
            "edge_types": [{"name": "knows", "source_targets": [{"source": "Character", "target": "Character"}]}],
        },
        db=AsyncMock(),
        progress_callback=lambda _progress, message: events.append(message),
    )

    assert graph_id.startswith("musegraph_")
    create_mock.assert_called_once()
    set_ontology_mock.assert_called_once()
    add_batch_mock.assert_called_once()
    assert episode_get_mock.call_count >= 1
    assert any("Graphiti" in message for message in events)


@pytest.mark.asyncio
async def test_build_graph_reuses_existing_graph(monkeypatch: pytest.MonkeyPatch):
    create_mock = MagicMock()
    add_batch_mock = MagicMock(return_value=[])
    fake_client = SimpleNamespace(
        graph=SimpleNamespace(
            create=create_mock,
            set_ontology=MagicMock(),
            add_batch=add_batch_mock,
            episode=SimpleNamespace(get=MagicMock()),
        )
    )

    monkeypatch.setattr(zep_graph, "_create_zep_client", lambda: fake_client)
    monkeypatch.setattr(zep_graph, "_import_zep_runtime", _fake_import_runtime)
    monkeypatch.setattr(
        zep_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(title="Demo", cognee_dataset_id="graph-existing")),
    )

    graph_id = await zep_graph.build_graph("proj-1", "text", db=AsyncMock())

    assert graph_id == "graph-existing"
    create_mock.assert_not_called()
    add_batch_mock.assert_called_once()


@pytest.mark.asyncio
async def test_search_graph_parses_edges_and_nodes(monkeypatch: pytest.MonkeyPatch):
    search_mock = MagicMock(
        return_value=SimpleNamespace(
            edges=[SimpleNamespace(uuid_="edge-1", fact="A knows B", name="KNOWS", score=0.8)],
            nodes=[SimpleNamespace(uuid_="node-1", name="Alice", summary="Alice summary", labels=["Entity", "Character"], score=0.6)],
        )
    )
    fake_client = SimpleNamespace(graph=SimpleNamespace(search=search_mock))

    monkeypatch.setattr(zep_graph, "_create_zep_client", lambda: fake_client)
    monkeypatch.setattr(
        zep_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(cognee_dataset_id="graph-1")),
    )

    results = await zep_graph.search_graph("proj-1", "who", db=AsyncMock(), top_k=5, search_type="INSIGHTS")

    assert results[0]["content"] == "A knows B"
    assert results[1]["type"] == "Character"
    search_mock.assert_called_once()


@pytest.mark.asyncio
async def test_get_graph_visualization_transforms_nodes_and_edges(monkeypatch: pytest.MonkeyPatch):
    node_get_mock = MagicMock(
        return_value=[
            SimpleNamespace(uuid_="node-1", name="Alice", labels=["Entity", "Character"], summary="hero", attributes={"role": "lead"}),
            SimpleNamespace(uuid_="node-2", name="Bob", labels=["Entity"], summary="friend", attributes={}),
        ]
    )
    edge_get_mock = MagicMock(
        return_value=[
            SimpleNamespace(
                uuid_="edge-1",
                source_node_uuid="node-1",
                target_node_uuid="node-2",
                name="KNOWS",
                fact="Alice knows Bob",
                attributes={},
            )
        ]
    )
    fake_client = SimpleNamespace(graph=SimpleNamespace(node=SimpleNamespace(get_by_graph_id=node_get_mock), edge=SimpleNamespace(get_by_graph_id=edge_get_mock)))

    monkeypatch.setattr(zep_graph, "_create_zep_client", lambda: fake_client)
    monkeypatch.setattr(
        zep_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(cognee_dataset_id="graph-1")),
    )

    payload = await zep_graph.get_graph_visualization("proj-1", db=AsyncMock())

    assert payload["nodes"][0]["label"] == "Alice"
    assert payload["edges"][0]["source"] == "node-1"
    assert payload["edges"][0]["label"] == "KNOWS"


@pytest.mark.asyncio
async def test_delete_graph_uses_project_graph_id(monkeypatch: pytest.MonkeyPatch):
    delete_mock = MagicMock()
    fake_client = SimpleNamespace(graph=SimpleNamespace(delete=delete_mock))

    monkeypatch.setattr(zep_graph, "_create_zep_client", lambda: fake_client)
    monkeypatch.setattr(
        zep_graph,
        "_load_project",
        AsyncMock(return_value=SimpleNamespace(cognee_dataset_id="graph-1")),
    )

    await zep_graph.delete_graph("proj-1", db=AsyncMock())

    delete_mock.assert_called_once_with(graph_id="graph-1")

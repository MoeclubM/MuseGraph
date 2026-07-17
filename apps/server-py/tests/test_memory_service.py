from __future__ import annotations

import pytest

from app.services.memory_service import memory_rag_query


@pytest.mark.asyncio
async def test_memory_rag_query_expands_graph_neighbors(monkeypatch):
    async def _search(project_id, query, *, top_k, db, operation_id=None):
        assert project_id == "proj-1"
        assert query == "铜钥匙"
        assert top_k == 3
        assert operation_id is None
        return [
            {
                "id": "memory-a",
                "type": "normal",
                "content": "林默发现铜钥匙。",
                "score": 0.91,
            }
        ]

    async def _export_project(project_id, *, db):
        assert project_id == "proj-1"
        return {
            "nodes": [
                {"id": "memory-a", "label": "林默", "type": "memory", "content": "林默发现铜钥匙。"},
                {"id": "memory-b", "label": "铜钥匙", "type": "object", "content": "抗腐蚀铜钥匙"},
            ],
            "edges": [
                {
                    "id": "edge-a-b",
                    "source": "memory-a",
                    "target": "memory-b",
                    "type": "RELATED_TO",
                    "label": "DISCOVERS",
                    "weight": 1.0,
                }
            ],
        }

    monkeypatch.setattr("app.services.memory_service.memory_backend.search", _search)
    monkeypatch.setattr("app.services.memory_service.memory_backend.export_project", _export_project)

    result = await memory_rag_query("proj-1", "铜钥匙", top_k=3, neighbor_depth=1, db=None)

    assert [node["id"] for node in result["entities"]] == ["memory-a", "memory-b"]
    assert result["relationships"] == [
        {
            "id": "edge-a-b",
            "source": "memory-a",
            "target": "memory-b",
            "type": "RELATED_TO",
            "label": "DISCOVERS",
            "weight": 1.0,
            "properties": {},
        }
    ]
    assert result["submemory"]["edges"] == result["relationships"]

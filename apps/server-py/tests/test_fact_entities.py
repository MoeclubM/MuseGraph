from __future__ import annotations

from types import SimpleNamespace

from app.services.fact_entities import (
    collect_project_entities,
    group_entities_by_type,
    merge_structured_memory,
    search_project_entities,
)


def _fact(*, fact_id: str, title: str, entities: list[dict] | None = None):
    return SimpleNamespace(
        id=fact_id,
        title=title,
        entities=entities or [],
    )


def test_collect_project_entities_from_facts_and_structured_memory():
    facts = [
        _fact(
            fact_id="f1",
            title="角色设定",
            entities=[{"id": "lin", "name": "林岚", "type": "Person", "summary": "主角"}],
        )
    ]
    structured_memory = {
        "organizations": [{"id": "acme", "name": "星港公司", "type": "Organization", "industry": "航天"}],
    }
    entities = collect_project_entities(
        facts=facts,
        structured_memory=structured_memory,
        ontology={"entity_types": [{"name": "Person"}, {"name": "Organization"}]},
    )
    names = {item["name"] for item in entities}
    assert names == {"林岚", "星港公司"}


def test_search_project_entities_prefers_name_matches():
    entities = collect_project_entities(
        facts=[
            _fact(
                fact_id="f1",
                title="设定",
                entities=[
                    {"id": "a", "name": "Alpha", "type": "Concept", "summary": "first"},
                    {"id": "b", "name": "Beta", "type": "Concept", "summary": "alpha variant"},
                ],
            )
        ]
    )
    results = search_project_entities(entities, query="Alpha", limit=5)
    assert [item["name"] for item in results] == ["Alpha", "Beta"]


def test_group_entities_by_type():
    entities = [
        {"id": "1", "name": "A", "type": "Person"},
        {"id": "2", "name": "B", "type": "Place"},
    ]
    groups = group_entities_by_type(entities)
    assert [group["type"] for group in groups] == ["Person", "Place"]


def test_merge_structured_memory_deep_merges_dicts():
    merged = merge_structured_memory(
        {"characters": {"hero": "Lin"}, "worldview": {"era": "future"}},
        {"characters": {"mentor": "Chen"}, "themes": ["hope"]},
    )
    assert merged["characters"] == {"hero": "Lin", "mentor": "Chen"}
    assert merged["themes"] == ["hope"]

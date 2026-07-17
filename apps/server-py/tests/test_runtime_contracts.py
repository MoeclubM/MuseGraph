import inspect
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.runtime import (
    AgentFinish,
    AgentRunRequest,
    ChangeSet,
    ConstraintRecord,
    CreationPlan,
    CreationPlanStep,
    EntityRecord,
    FactRecord,
    KnowledgeUpsert,
    RelationRecord,
    SourceRef,
)
from app.services.agent.pack_core import list_packs, load_pack
from app.services.agent.skill_catalog import ALL_AGENT_TOOLS, BUILTIN_SKILL_MAP
from app.services.agent.skills import (
    ROLE_NAMES,
    validate_pack_skill_references,
    validate_skill_definition,
)
from app.services.agent.tool_registry import TOOL_REGISTRY
from app.services.agent_engine import _validate_changes
from app.services.agent_workspace import apply_knowledge_operations


def test_tool_registry_schema_handler_and_role_contracts_are_complete():
    assert set(TOOL_REGISTRY) == ALL_AGENT_TOOLS
    assert {"web_search", "fetch_url"}.isdisjoint(TOOL_REGISTRY)
    for name, definition in TOOL_REGISTRY.items():
        assert definition.name == name
        assert inspect.iscoroutinefunction(definition.handler)
        assert definition.roles
        assert definition.roles <= ROLE_NAMES
        schema = definition.json_schema()
        assert schema["name"] == name
        assert schema["parameters"]["additionalProperties"] is False
    assert TOOL_REGISTRY["write_file"].roles == {"writer", "reviser"}
    assert TOOL_REGISTRY["knowledge_upsert"].roles == {
        "updater",
        "memory_builder",
        "graph_extractor",
    }


def test_all_text_packs_have_strict_complete_creation_metadata():
    validate_pack_skill_references()
    descriptors = list_packs()
    assert {item["text_type"] for item in descriptors} == {
        "generic",
        "novel",
        "article",
        "paper",
        "screenplay",
        "product_doc",
    }
    for descriptor in descriptors:
        pack = load_pack(descriptor["text_type"])
        assert set(pack.control_docs) == {"intent", "focus", "rules", "bible"}
        assert pack.auditor_dimensions
        assert pack.knowledge_types
        assert pack.unit["name"]
        assert set(pack.default_skills.values()) <= set(BUILTIN_SKILL_MAP)


def test_custom_skill_cannot_override_builtin_or_expand_registry():
    with pytest.raises(ValueError, match="cannot override"):
        validate_skill_definition(
            slug="general",
            scopes=["write"],
            roles=["writer"],
            allowed_tools=["write_file"],
            default_model_component=None,
            params_schema={"type": "object"},
        )
    with pytest.raises(ValueError, match="Unknown or disallowed tools"):
        validate_skill_definition(
            slug="unsafe",
            scopes=["write"],
            roles=["writer"],
            allowed_tools=["shell"],
            default_model_component=None,
            params_schema={"type": "object"},
        )


def test_public_runtime_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        AgentRunRequest(
            instruction="Analyze the project",
            mode="analyze",
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        CreationPlan(
            objective="Write",
            steps=[
                CreationPlanStep(
                    goal="Draft",
                    role="writer",
                    expected_output="chapter.md",
                )
            ],
            legacy_finish=True,
        )


def test_knowledge_union_requires_sources_and_relation_integrity():
    source = SourceRef(kind="file", ref="bible.md")
    hero = EntityRecord(
        id="entity:hero",
        kind="entity",
        title="Hero",
        content="The protagonist",
        entity_type="character",
        source_refs=[source],
    )
    city = EntityRecord(
        id="entity:city",
        kind="entity",
        title="City",
        content="Primary setting",
        entity_type="place",
        source_refs=[source],
    )
    relation = RelationRecord(
        id="relation:hero-city",
        kind="relation",
        title="Hero lives in city",
        content="The hero lives in the city",
        source_id=hero.id,
        target_id=city.id,
        predicate="lives_in",
        source_refs=[source],
    )
    records = apply_knowledge_operations(
        [],
        [
            KnowledgeUpsert(record=hero),
            KnowledgeUpsert(record=city),
            KnowledgeUpsert(record=relation),
        ],
        "revision-1",
    )
    assert [record["id"] for record in records] == [
        "entity:city",
        "entity:hero",
        "relation:hero-city",
    ]
    with pytest.raises(ValueError, match="Relation source does not exist"):
        apply_knowledge_operations(
            [],
            [KnowledgeUpsert(record=relation)],
            "revision-1",
        )
    with pytest.raises(ValidationError):
        FactRecord(
            id="fact:missing-source",
            kind="fact",
            title="No source",
            content="Invalid",
            source_refs=[],
        )


def test_finish_must_prove_planned_knowledge_and_required_constraints_were_used():
    finish = AgentFinish(
        summary="Drafted",
        changed_files=["chapter.md"],
        knowledge_operations=0,
        used_knowledge_ids=["fact:weather"],
    )
    validation = _validate_changes(
        SimpleNamespace(mode="write"),
        finish,
        ChangeSet(
            files=[
                {
                    "path": "chapter.md",
                    "change_type": "modified",
                    "before_hash": "before",
                    "after_hash": "after",
                    "diff": "changed",
                }
            ]
        ),
        {"fact:weather", "constraint:voice"},
        {"constraint:voice"},
        {"fact:weather"},
    )
    assert validation.passed is False
    failed = {check["name"] for check in validation.checks if not check["passed"]}
    assert failed == {"required_constraints_used"}

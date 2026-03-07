from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import simulation as simulation_router


@pytest.mark.asyncio
async def test_build_run_artifacts_with_llm_generates_posts_and_actions(monkeypatch: pytest.MonkeyPatch):
    sim = SimpleNamespace(
        simulation_id="sim_123",
        user_id="user-1",
        profiles=[{"name": "AgentA", "role": "analyst"}, {"name": "AgentB", "role": "critic"}],
        simulation_config={
            "active_platforms": ["twitter", "reddit"],
            "time_config": {"total_hours": 4, "minutes_per_round": 60},
            "events": [{"title": "launch", "trigger_hour": 1, "description": "start"}],
            "agent_activity": [{"name": "AgentA", "posts_per_hour": 1.2}],
        },
    )
    project = SimpleNamespace(
        id="proj-1",
        simulation_requirement="focus on stakeholder conflict",
        oasis_analysis={
            "scenario_summary": "A product launch under public pressure",
            "continuation_guidance": {"must_follow": ["keep consistency"]},
        },
        component_models={"oasis_simulation": "model-sim"},
    )
    run_result = {"metrics": {"total_rounds": 2}}

    async def _fake_call_llm(*, model: str, prompt: str, db, max_tokens: int):
        assert model == "model-sim"
        return {
            "content": (
                '{"rounds":['
                '{"round":1,"posts":[{"agent":"AgentA","platform":"twitter","content":"Round 1 post"}],"comments":[],"actions":[]},'
                '{"round":2,"posts":[{"agent":"AgentB","platform":"reddit","content":"Round 2 post"}],"comments":[{"agent":"AgentA","platform":"reddit","content":"Round 2 comment"}],"actions":[{"agent":"AgentB","action_type":"react","summary":"liked trend"}]}'
                ']}'
            )
        }

    monkeypatch.setattr(simulation_router, "call_llm", _fake_call_llm)

    generated = await simulation_router._build_run_artifacts_with_llm(
        sim=sim,
        project=project,
        run_result=run_result,
        max_rounds=2,
        db=AsyncMock(),
    )

    assert generated is not None
    enriched, posts, comments, actions = generated
    assert len(posts) == 2
    assert len(comments) == 1
    assert len(actions) >= 3
    assert enriched["metrics"]["generated_mode"] == "llm"
    assert "highlights" not in enriched


@pytest.mark.asyncio
async def test_build_run_artifacts_with_llm_raises_when_invalid_json(monkeypatch: pytest.MonkeyPatch):
    sim = SimpleNamespace(
        simulation_id="sim_456",
        user_id="user-2",
        profiles=[{"name": "AgentA", "role": "analyst"}],
        simulation_config={"active_platforms": ["twitter"], "events": [], "agent_activity": []},
    )
    project = SimpleNamespace(
        id="proj-2",
        simulation_requirement="",
        oasis_analysis={},
        component_models={"oasis_simulation": "model-sim"},
    )
    run_result = {"metrics": {"total_rounds": 1}}

    async def _fake_call_llm(*, model: str, prompt: str, db, max_tokens: int):
        return {"content": "not-json"}

    monkeypatch.setattr(simulation_router, "call_llm", _fake_call_llm)

    with pytest.raises(ValueError, match="simulation_run_llm_response_not_json_or_invalid_schema"):
        await simulation_router._build_run_artifacts_with_llm(
            sim=sim,
            project=project,
            run_result=run_result,
            max_rounds=1,
            db=AsyncMock(),
        )

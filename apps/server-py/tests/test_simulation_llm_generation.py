from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import simulation as simulation_router


@pytest.mark.asyncio
async def test_build_run_artifacts_with_llm_generates_posts_and_actions(monkeypatch: pytest.MonkeyPatch):
    sim = SimpleNamespace(
        simulation_id="sim_123",
        profiles=[{"name": "AgentA", "role": "analyst"}, {"name": "AgentB", "role": "critic"}],
        simulation_config={
            "active_platforms": ["twitter", "reddit"],
            "time_config": {"total_hours": 4, "minutes_per_round": 60},
            "events": [{"title": "launch", "trigger_hour": 1, "description": "start"}],
            "agent_activity": [{"name": "AgentA", "posts_per_hour": 1.2}],
        },
    )
    project = SimpleNamespace(
        simulation_requirement="focus on stakeholder conflict",
        oasis_analysis={
            "scenario_summary": "A product launch under public pressure",
            "continuation_guidance": {"must_follow": ["keep consistency"]},
            "key_drivers": ["trust", "cost"],
            "risk_signals": ["backlash"],
        },
        component_models={"oasis_simulation": "model-sim"},
    )
    run_result = {"metrics": {"total_rounds": 2}}

    async def _fake_call_llm(*, model: str, prompt: str, db):
        assert model == "model-sim"
        return {
            "content": (
                '{"rounds":['
                '{"round":1,"posts":[{"agent":"AgentA","platform":"twitter","content":"Round 1 post"}],"comments":[],"actions":[]},'
                '{"round":2,"posts":[{"agent":"AgentB","platform":"reddit","content":"Round 2 post"}],"comments":[{"agent":"AgentA","platform":"reddit","content":"Round 2 comment"}],"actions":[{"agent":"AgentB","action_type":"react","summary":"liked trend"}]}'
                '],"highlights":["H1"]}'
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
    assert enriched["highlights"] == ["H1"]


@pytest.mark.asyncio
async def test_build_run_artifacts_with_llm_returns_none_when_invalid_json(monkeypatch: pytest.MonkeyPatch):
    sim = SimpleNamespace(
        simulation_id="sim_456",
        profiles=[{"name": "AgentA", "role": "analyst"}],
        simulation_config={"active_platforms": ["twitter"], "events": [], "agent_activity": []},
    )
    project = SimpleNamespace(
        simulation_requirement="",
        oasis_analysis={},
        component_models={"oasis_simulation": "model-sim"},
    )
    run_result = {"metrics": {"total_rounds": 1}}

    async def _fake_call_llm(*, model: str, prompt: str, db):
        return {"content": "not-json"}

    monkeypatch.setattr(simulation_router, "call_llm", _fake_call_llm)

    generated = await simulation_router._build_run_artifacts_with_llm(
        sim=sim,
        project=project,
        run_result=run_result,
        max_rounds=1,
        db=AsyncMock(),
    )

    assert generated is None

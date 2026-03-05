from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import prediction


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


class TestPredictionHelpers:
    """Test prediction service helper functions."""

    def test_safe_list_with_list(self):
        """Test _safe_list with valid list."""
        result = prediction._safe_list(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_safe_list_with_limit(self):
        """Test _safe_list respects limit."""
        result = prediction._safe_list(["a", "b", "c", "d", "e"], limit=3)
        assert result == ["a", "b", "c"]

    def test_safe_list_with_non_list(self):
        """Test _safe_list with non-list input."""
        result = prediction._safe_list("not a list")
        assert result == []

    def test_safe_list_with_none(self):
        """Test _safe_list with None input."""
        result = prediction._safe_list(None)
        assert result == []

    def test_safe_list_filters_empty_strings(self):
        """Test _safe_list filters empty strings."""
        result = prediction._safe_list(["a", "", "b", "  ", "c"])
        assert result == ["a", "b", "c"]

    def test_format_oasis_context_empty(self):
        """Test _format_oasis_context with empty input."""
        result = prediction._format_oasis_context(None)
        assert result == ""

    def test_format_oasis_context_non_dict(self):
        """Test _format_oasis_context with non-dict input."""
        result = prediction._format_oasis_context("not a dict")
        assert result == ""

    def test_format_oasis_context_with_summary(self):
        """Test _format_oasis_context with summary."""
        oasis = {"scenario_summary": "Test scenario"}
        result = prediction._format_oasis_context(oasis)
        assert "Test scenario" in result

    def test_format_oasis_context_with_guidance(self):
        """Test _format_oasis_context with continuation guidance."""
        oasis = {
            "continuation_guidance": {
                "must_follow": ["Rule 1", "Rule 2"],
                "next_steps": ["Step 1"],
                "avoid": ["Don't do this"],
            }
        }
        result = prediction._format_oasis_context(oasis)
        assert "Must-follow constraints" in result
        assert "Rule 1" in result
        assert "Suggested next steps" in result
        assert "Avoid" in result

    def test_format_oasis_context_with_agents(self):
        """Test _format_oasis_context with agent profiles."""
        oasis = {
            "agent_profiles": [
                {"name": "Agent A", "role": "Leader", "stance": "Supportive"},
                {"name": "Agent B", "role": "Critic", "stance": "Skeptical"},
            ]
        }
        result = prediction._format_oasis_context(oasis)
        assert "Agent profile anchors" in result
        assert "Agent A" in result

    def test_format_structure_context_empty(self):
        """Test _format_structure_context with empty input."""
        result = prediction._format_structure_context(None)
        assert result == ""

    def test_format_structure_context_with_narrative_dict(self):
        """Test _format_structure_context with narrative dict."""
        structure = {
            "narrative_state": {"phase": "rising action", "summary": "Things happen"}
        }
        result = prediction._format_structure_context(structure)
        assert "rising action: Things happen" in result

    def test_format_structure_context_with_entities(self):
        """Test _format_structure_context with core entities."""
        structure = {
            "core_entities": [
                {"name": "Hero", "role": "Protagonist", "state": "Active"},
            ]
        }
        result = prediction._format_structure_context(structure)
        assert "Core entities" in result
        assert "Hero" in result

    def test_format_structure_context_with_conflicts(self):
        """Test _format_structure_context with conflicts."""
        structure = {"active_conflicts": ["Conflict 1", "Conflict 2"]}
        result = prediction._format_structure_context(structure)
        assert "Active conflicts" in result
        assert "Conflict 1" in result

    def test_build_reference_rag_context_with_alias_trigger(self):
        """Glossary aliases should expand retrieval anchors."""
        reference_cards = {
            "characters": [
                {"id": "c1", "name": "林默", "role": "侦探", "profile": "理性克制", "notes": "怕海"},
            ],
            "glossary_terms": [
                {
                    "id": "g1",
                    "term": "回声井",
                    "definition": "旧城地下结构",
                    "aliases": ["回声点", "Echo Well"],
                    "notes": "涉及主线",
                }
            ],
            "worldbook_entries": [
                {
                    "id": "w1",
                    "title": "旧城下水道",
                    "category": "地点",
                    "content": "潮汐期间会封闭闸门",
                    "tags": ["地下", "闸门"],
                    "notes": "",
                }
            ],
            "explicit_glossary_term_ids": ["g1"],
        }
        context = prediction.build_reference_rag_context(
            reference_cards,
            focus_text="林默昨晚在回声点附近看到了闸门异动",
        )
        assert context["character_lines"]
        assert context["glossary_lines"]
        assert any("回声点 -> 回声井" in row for row in context["alias_expansions"])
        assert "回声井" in context["query_terms"]
        assert "林默" in context["query_terms"]

    def test_build_retrieval_query_groups(self):
        groups = prediction._build_retrieval_query_groups(
            focus_text="林默在回声点调查旧城闸门",
            reference_context={
                "query_terms": ["林默", "回声井", "旧城下水道", "闸门"],
                "alias_expansions": ["回声点 -> 回声井"],
            },
        )
        assert groups
        assert any("林默" in row for row in groups)
        assert any("回声井" in row for row in groups)

    def test_rank_search_rows_filters_low_relevance(self):
        rows = [
            {"content": "林默在旧城闸门前发现异常脚印", "score": 0.8, "type": "DocumentChunk"},
            {"content": "完全无关的厨房清单", "score": 0.1, "type": "DocumentChunk"},
        ]
        ranked = prediction._rank_search_rows(
            rows,
            focus_text="林默在闸门调查",
            limit=5,
            max_chars=120,
            require_overlap_for_low_score=True,
        )
        assert ranked
        assert any("林默" in row for row in ranked)
        assert all("厨房清单" not in row for row in ranked)


class TestBuildPredictionPrompt:
    """Test build_prediction_prompt function."""

    def test_build_prompt_returns_base_when_no_context(self):
        """Test returns base prompt when no context available."""
        result = prediction.build_prediction_prompt(
            input_text="Test input",
            graph_context={"insights": [], "relationships": []},
            oasis_analysis=None,
            simulation_requirement=None,
            structure_analysis=None,
            base_prompt="Base prompt",
        )
        assert result == "Base prompt"

    def test_build_prompt_enhances_with_graph_context(self):
        """Test enhances prompt with graph context."""
        result = prediction.build_prediction_prompt(
            input_text="Test input",
            graph_context={"insights": ["Insight 1"], "relationships": ["Rel 1"]},
            oasis_analysis=None,
            simulation_requirement=None,
            structure_analysis=None,
            base_prompt="Base prompt",
        )
        assert "Knowledge Graph Context" in result
        assert "Insight 1" in result

    def test_build_prompt_includes_simulation_requirement(self):
        """Test includes simulation requirement."""
        result = prediction.build_prediction_prompt(
            input_text="Test input",
            graph_context={"insights": [], "relationships": []},
            oasis_analysis=None,
            simulation_requirement="Must be realistic",
            structure_analysis=None,
            base_prompt="Base prompt",
        )
        assert "Must be realistic" in result

    def test_build_prompt_includes_reference_rag_context(self):
        """Reference RAG blocks should appear in the enhanced prompt."""
        result = prediction.build_prediction_prompt(
            input_text="Test input",
            graph_context={"insights": [], "relationships": []},
            oasis_analysis=None,
            simulation_requirement=None,
            structure_analysis=None,
            base_prompt="Base prompt",
            reference_rag_context={
                "character_lines": ["- 林默: 侦探"],
                "glossary_lines": ["- 回声井 | definition: 地下结构"],
                "worldbook_lines": [],
                "query_terms": ["林默", "回声井"],
                "alias_expansions": [],
            },
        )
        assert "Reference characters" in result
        assert "回声井" in result


class TestGetEnhancedPrompt:
    """Test get_enhanced_prompt function."""

    @pytest.mark.asyncio
    async def test_get_enhanced_prompt_non_continue_op(self):
        """Unsupported operation type should return base prompt."""
        mock_db = AsyncMock()

        result = await prediction.get_enhanced_prompt(
            project_id="proj-1",
            op_type="EXPORT",
            input_text="Test",
            base_prompt="Base",
            db=mock_db,
        )
        assert result == "Base"

    @pytest.mark.asyncio
    async def test_get_enhanced_prompt_project_not_found(self):
        """Test returns base when project not found."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await prediction.get_enhanced_prompt(
            project_id="proj-1",
            op_type="CONTINUE",
            input_text="Test",
            base_prompt="Base",
            db=mock_db,
        )
        assert result == "Base"

    @pytest.mark.asyncio
    async def test_get_enhanced_prompt_no_context(self):
        """Test returns base when no context available."""
        mock_db = AsyncMock()

        project = SimpleNamespace(
            cognee_dataset_id=None,
            oasis_analysis=None,
            simulation_requirement=None,
            component_models=None,
            title="Test",
            description="",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = project
        mock_db.execute.return_value = mock_result

        with patch("app.services.prediction.analyze_structure", return_value=None):
            result = await prediction.get_enhanced_prompt(
                project_id="proj-1",
                op_type="CONTINUE",
                input_text="Test",
                base_prompt="Base",
                db=mock_db,
            )
        assert result == "Base"


@pytest.mark.asyncio
async def test_get_enhanced_prompt_uses_structure_analysis_without_graph(monkeypatch: pytest.MonkeyPatch):
    fake_project = SimpleNamespace(
        id="p1",
        title="Story",
        description="desc",
        simulation_requirement="must keep tone realistic",
        component_models={"operation_analyze": "model-analyze"},
        oasis_analysis=None,
        cognee_dataset_id=None,
    )
    fake_db = AsyncMock()
    fake_db.execute.return_value = _scalar_one_or_none(fake_project)

    async def _fake_call_llm(*, model: str, prompt: str, db):
        assert model == "model-analyze"
        return {
            "content": (
                '{"narrative_state":{"phase":"rising action","summary":"stake escalates"},'
                '"core_entities":[{"name":"Hero","role":"lead","state":"under pressure"}],'
                '"active_conflicts":["trust breakdown"],'
                '"hard_constraints":["keep first person"],'
                '"style_anchors":["concise"],'
                '"next_beats":["escalate conflict"],'
                '"unknowns":["who leaked the plan"]}'
            )
        }

    monkeypatch.setattr("app.services.ai.call_llm", _fake_call_llm)

    prompt = await prediction.get_enhanced_prompt(
        project_id="p1",
        op_type="CREATE",
        input_text="I arrived late to the station.",
        base_prompt="BASE_PROMPT",
        db=fake_db,
    )

    assert prompt != "BASE_PROMPT"
    assert "Narrative structure analysis" in prompt
    assert "trust breakdown" in prompt
    assert "Simulation requirement" in prompt


@pytest.mark.asyncio
async def test_get_enhanced_prompt_returns_base_when_no_context(monkeypatch: pytest.MonkeyPatch):
    fake_project = SimpleNamespace(
        id="p2",
        title="Story",
        description="desc",
        simulation_requirement="",
        component_models={"operation_analyze": "model-analyze"},
        oasis_analysis=None,
        cognee_dataset_id=None,
    )
    fake_db = AsyncMock()
    fake_db.execute.return_value = _scalar_one_or_none(fake_project)

    async def _fake_call_llm(*, model: str, prompt: str, db):
        return {"content": '{"narrative_state":{"phase":"","summary":""},"core_entities":[],"active_conflicts":[],"hard_constraints":[],"style_anchors":[],"next_beats":[],"unknowns":[]}'}

    monkeypatch.setattr("app.services.ai.call_llm", _fake_call_llm)

    prompt = await prediction.get_enhanced_prompt(
        project_id="p2",
        op_type="CONTINUE",
        input_text="",
        base_prompt="BASE_PROMPT",
        db=fake_db,
    )

    assert prompt == "BASE_PROMPT"


@pytest.mark.asyncio
async def test_get_enhanced_prompt_uses_reference_cards_without_graph(monkeypatch: pytest.MonkeyPatch):
    fake_project = SimpleNamespace(
        id="p3",
        title="Story",
        description="desc",
        simulation_requirement="",
        component_models={"operation_analyze": "model-analyze"},
        oasis_analysis=None,
        cognee_dataset_id=None,
    )
    fake_db = AsyncMock()
    fake_db.execute.return_value = _scalar_one_or_none(fake_project)

    async def _fake_call_llm(*, model: str, prompt: str, db):
        return {"content": '{"narrative_state":{"phase":"","summary":""},"core_entities":[],"active_conflicts":[],"hard_constraints":[],"style_anchors":[],"next_beats":[],"unknowns":[]}'}

    monkeypatch.setattr("app.services.ai.call_llm", _fake_call_llm)

    prompt = await prediction.get_enhanced_prompt(
        project_id="p3",
        op_type="CONTINUE",
        input_text="林默调查回声点",
        base_prompt="BASE_PROMPT",
        db=fake_db,
        reference_cards={
            "characters": [{"id": "c1", "name": "林默", "role": "侦探"}],
            "glossary_terms": [{"id": "g1", "term": "回声井", "aliases": ["回声点"], "definition": "地下设施"}],
            "worldbook_entries": [],
            "explicit_character_ids": ["c1"],
            "explicit_glossary_term_ids": ["g1"],
        },
    )

    assert prompt != "BASE_PROMPT"
    assert "Reference glossary terms" in prompt

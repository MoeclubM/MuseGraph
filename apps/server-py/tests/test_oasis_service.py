"""Tests for OASIS simulation service functions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.oasis import (
    _as_text_list,
    _fallback_profiles_from_ontology,
    _fallback_report_markdown,
    _safe_agent_activity,
    _safe_agent_profiles,
    _safe_list,
    _to_float,
    _to_int,
    build_oasis_package,
    build_oasis_run_result,
    fallback_oasis_analysis,
    normalize_oasis_config,
    sanitize_oasis_analysis,
    sanitize_oasis_simulation_config,
)


class TestHelperFunctions:
    """Test helper functions in oasis.py."""

    def test_as_text_list_with_valid_items(self):
        """Test _as_text_list extracts content from items."""
        items = [
            {"content": "First item"},
            {"content": "Second item"},
            {"content": ""},
            {"content": "  Third item  "},
            {},
        ]
        result = _as_text_list(items)
        assert result == ["First item", "Second item", "Third item"]

    def test_as_text_list_empty(self):
        """Test _as_text_list with empty list."""
        assert _as_text_list([]) == []

    def test_safe_list_with_valid_list(self):
        """Test _safe_list processes list items."""
        items = ["  item1  ", "item2", "", "item3"]
        result = _safe_list(items, max_items=2)
        assert result == ["item1", "item2"]

    def test_safe_list_with_non_list(self):
        """Test _safe_list with non-list input."""
        assert _safe_list("not a list") == []
        assert _safe_list(None) == []
        assert _safe_list({"key": "value"}) == []

    def test_safe_list_max_items(self):
        """Test _safe_list respects max_items."""
        items = ["a", "b", "c", "d", "e"]
        result = _safe_list(items, max_items=3)
        assert len(result) == 3

    def test_safe_agent_profiles_valid(self):
        """Test _safe_agent_profiles with valid profiles."""
        profiles = [
            {"name": "Agent1", "role": "User", "persona": "Persona1", "stance": "supportive"},
            {"name": "Agent2", "role": "Admin", "persona": "Persona2"},
        ]
        result = _safe_agent_profiles(profiles)
        assert len(result) == 2
        assert result[0]["name"] == "Agent1"
        assert result[0]["stance"] == "supportive"
        assert result[1]["stance"] == "neutral"

    def test_safe_agent_profiles_missing_name(self):
        """Test _safe_agent_profiles skips profiles without name."""
        profiles = [
            {"name": "", "role": "User"},
            {"name": "Valid", "role": "Admin"},
            {"role": "NoName"},
        ]
        result = _safe_agent_profiles(profiles)
        assert len(result) == 1
        assert result[0]["name"] == "Valid"

    def test_safe_agent_profiles_non_list(self):
        """Test _safe_agent_profiles with non-list input."""
        assert _safe_agent_profiles(None) == []
        assert _safe_agent_profiles("not a list") == []

    def test_safe_agent_profiles_max_items(self):
        """Test _safe_agent_profiles respects max_items."""
        profiles = [{"name": f"Agent{i}"} for i in range(20)]
        result = _safe_agent_profiles(profiles, max_items=5)
        assert len(result) == 5

    def test_safe_agent_activity_valid(self):
        """Test _safe_agent_activity with valid data."""
        activities = [
            {"name": "Agent1", "activity_level": 0.8, "posts_per_hour": 2.5, "response_delay_minutes": 30},
            {"name": "Agent2", "activity_level": 1.5, "posts_per_hour": 25, "response_delay_minutes": 1000},
        ]
        result = _safe_agent_activity(activities)
        assert len(result) == 2
        # Check clamping
        assert result[1]["activity_level"] == 1.0  # max 1.0
        assert result[1]["posts_per_hour"] == 20.0  # max 20.0
        assert result[1]["response_delay_minutes"] == 720  # max 720

    def test_safe_agent_activity_missing_name(self):
        """Test _safe_agent_activity skips items without name."""
        activities = [
            {"activity_level": 0.5},
            {"name": "Valid", "activity_level": 0.5},
        ]
        result = _safe_agent_activity(activities)
        assert len(result) == 1

    def test_to_float(self):
        """Test _to_float conversion."""
        assert _to_float("3.14") == 3.14
        assert _to_float(3.14) == 3.14
        assert _to_float("invalid", default=1.0) == 1.0
        assert _to_float(None, default=2.0) == 2.0

    def test_to_int(self):
        """Test _to_int conversion."""
        assert _to_int("42") == 42
        assert _to_int(42) == 42
        assert _to_int("invalid", default=10) == 10
        assert _to_int(None, default=5) == 5

    def test_normalize_oasis_config_defaults_include_llm_retry(self):
        cfg = normalize_oasis_config(None)
        assert cfg["llm_request_timeout_seconds"] == 120
        assert cfg["llm_retry_count"] == 2
        assert cfg["llm_retry_interval_seconds"] == 1.5

    def test_normalize_oasis_config_clamps_llm_retry(self):
        cfg = normalize_oasis_config(
            {
                "llm_request_timeout_seconds": 9999,
                "llm_retry_count": -5,
                "llm_retry_interval_seconds": 999,
            }
        )
        assert cfg["llm_request_timeout_seconds"] == 1800
        assert cfg["llm_retry_count"] == 0
        assert cfg["llm_retry_interval_seconds"] == 60.0


class TestSanitizeOasisSimulationConfig:
    """Test sanitize_oasis_simulation_config function."""

    def test_sanitize_with_valid_data(self):
        """Test sanitize with valid configuration."""
        data = {
            "active_platforms": ["twitter", "reddit"],
            "time_config": {
                "total_hours": 48,
                "minutes_per_round": 30,
                "peak_hours": [9, 10, 11],
                "off_peak_hours": [0, 1, 2],
            },
            "events": [
                {"title": "Event1", "trigger_hour": 12, "description": "Test event"}
            ],
            "agent_activity": [
                {"name": "Agent1", "activity_level": 0.5, "posts_per_hour": 1.0, "response_delay_minutes": 60}
            ],
        }
        profiles = [{"name": "Agent1"}]
        result = sanitize_oasis_simulation_config(data, profiles)

        assert result["active_platforms"] == ["twitter", "reddit"]
        assert result["time_config"]["total_hours"] == 48
        assert result["time_config"]["minutes_per_round"] == 30
        assert len(result["events"]) == 1

    def test_sanitize_clamps_values(self):
        """Test sanitize clamps out-of-range values."""
        data = {
            "time_config": {
                "total_hours": 500,  # > 336
                "minutes_per_round": 5,  # < 10
            },
            "events": [
                {"title": "Event", "trigger_hour": 200}  # > 168
            ],
        }
        result = sanitize_oasis_simulation_config(data, [])

        assert result["time_config"]["total_hours"] == 336
        assert result["time_config"]["minutes_per_round"] == 10
        assert result["events"][0]["trigger_hour"] == 168

    def test_sanitize_defaults_platforms(self):
        """Test sanitize defaults platforms when empty."""
        data = {"active_platforms": []}
        result = sanitize_oasis_simulation_config(data, [])
        assert result["active_platforms"] == ["twitter", "reddit"]

    def test_sanitize_generates_agent_activity(self):
        """Test sanitize generates agent_activity from profiles when missing."""
        profiles = [
            {"name": "Agent1", "stance": "supportive"},
            {"name": "Agent2", "stance": "opposed"},
        ]
        result = sanitize_oasis_simulation_config({}, profiles)

        assert len(result["agent_activity"]) == 2
        assert result["agent_activity"][0]["name"] == "Agent1"


class TestSanitizeOasisAnalysis:
    """Test sanitize_oasis_analysis function."""

    def test_sanitize_analysis_with_valid_data(self):
        """Test sanitize_analysis with valid data."""
        data = {
            "scenario_summary": "Test scenario",
            "key_drivers": ["driver1", "driver2"],
            "risk_signals": ["risk1"],
            "opportunity_signals": ["opp1"],
            "timeline": ["event1"],
            "continuation_guidance": {
                "must_follow": ["rule1"],
                "next_steps": ["step1"],
                "avoid": ["avoid1"],
            },
            "agent_profiles": [{"name": "Agent1", "role": "User"}],
        }
        graph_context = {"insights": ["i1"], "relationships": ["r1"]}
        result = sanitize_oasis_analysis(data, graph_context)

        assert result["scenario_summary"] == "Test scenario"
        assert result["key_drivers"] == ["driver1", "driver2"]
        assert result["evidence"]["insight_count"] == 1

    def test_sanitize_analysis_with_missing_data(self):
        """Test sanitize_analysis with missing data."""
        result = sanitize_oasis_analysis({}, {})
        assert result["scenario_summary"] == ""
        assert result["key_drivers"] == []


class TestFallbackOasisAnalysis:
    """Test fallback_oasis_analysis function."""

    def test_fallback_with_requirement(self):
        """Test fallback analysis includes requirement."""
        ontology = {"entity_types": [{"name": "Entity1"}]}
        graph_context = {"risk_signals": ["risk1"], "insights": ["insight1"]}
        result = fallback_oasis_analysis("Test requirement", ontology, graph_context)

        assert "Test requirement" in result["continuation_guidance"]["must_follow"][0]
        assert "Entity1" in result["key_drivers"]

    def test_fallback_without_requirement(self):
        """Test fallback analysis without requirement."""
        result = fallback_oasis_analysis(None, None, {})
        assert result["scenario_summary"] != ""
        assert result["simulation_config"]["active_platforms"] == ["twitter", "reddit"]


class TestBuildOasisPackage:
    """Test build_oasis_package function."""

    def test_build_package_with_analysis(self):
        """Test build package with existing analysis."""
        analysis = {
            "scenario_summary": "Test summary",
            "continuation_guidance": {"must_follow": ["rule1"]},
            "agent_profiles": [{"name": "Agent1"}],
            "simulation_config": {"active_platforms": ["twitter"]},
        }
        result = build_oasis_package(
            project_id="proj-1",
            project_title="Test Project",
            requirement="Test requirement",
            ontology={"entity_types": []},
            analysis=analysis,
            component_models={"oasis_report": "gpt-4o"},
        )

        assert result["project_id"] == "proj-1"
        assert result["project_title"] == "Test Project"
        assert result["simulation_requirement"] == "Test requirement"
        assert len(result["profiles"]) == 1
        assert result["component_models"]["oasis_report"] == "gpt-4o"

    def test_build_package_without_profiles_uses_ontology(self):
        """Test build package uses ontology when no profiles."""
        ontology = {
            "entity_types": [
                {"name": "Person", "description": "A person"},
                {"name": "Organization", "description": "An org"},
            ]
        }
        result = build_oasis_package(
            project_id="proj-1",
            project_title="Test",
            requirement=None,
            ontology=ontology,
            analysis=None,
        )

        assert len(result["profiles"]) == 2
        assert "Person_AGENT" in result["profiles"][0]["name"]


class TestBuildOasisRunResult:
    """Test build_oasis_run_result function."""

    def test_build_run_result_basic(self):
        """Test basic run result generation."""
        package = {
            "simulation_id": "sim-1",
            "simulation_config": {
                "time_config": {
                    "total_hours": 24,
                    "minutes_per_round": 60,
                },
                "events": [
                    {"title": "Event1", "trigger_hour": 5, "description": "Test"}
                ],
                "agent_activity": [
                    {"name": "Agent1", "posts_per_hour": 2.0}
                ],
            },
            "profiles": [{"name": "Agent1"}],
        }
        result = build_oasis_run_result(package=package, analysis=None)

        assert result["simulation_id"] == "sim-1"
        assert result["status"] == "completed"
        assert result["metrics"]["total_hours"] == 24
        assert result["metrics"]["total_rounds"] == 24
        assert len(result["triggered_events"]) == 1

    def test_build_run_result_with_analysis(self):
        """Test run result with analysis data."""
        package = {"simulation_config": {}}
        analysis = {
            "risk_signals": ["risk1", "risk2"],
            "opportunity_signals": ["opp1"],
        }
        result = build_oasis_run_result(package=package, analysis=analysis)

        assert "risk1" in result["risk_signals"]
        assert "opp1" in result["opportunity_signals"]


class TestFallbackReportMarkdown:
    """Test _fallback_report_markdown function."""

    def test_fallback_markdown_basic(self):
        """Test basic markdown generation."""
        analysis = {"scenario_summary": "Test summary"}
        run_result = {"metrics": {"total_hours": 48, "total_rounds": 24}}
        markdown = _fallback_report_markdown(
            requirement="Test requirement",
            analysis=analysis,
            run_result=run_result,
        )

        assert "# OASIS Analysis Report" in markdown
        assert "Test summary" in markdown
        assert "Test requirement" in markdown
        assert "48" in markdown

    def test_fallback_markdown_with_signals(self):
        """Test markdown with risk and opportunity signals."""
        analysis = {
            "scenario_summary": "Summary",
            "risk_signals": ["Risk 1", "Risk 2"],
            "opportunity_signals": ["Opp 1"],
            "continuation_guidance": {"next_steps": ["Step 1", "Step 2"]},
        }
        markdown = _fallback_report_markdown(
            requirement=None,
            analysis=analysis,
            run_result=None,
        )

        assert "## Risk Signals" in markdown
        assert "- Risk 1" in markdown
        assert "## Opportunity Signals" in markdown
        assert "## Recommended Next Steps" in markdown


class TestAsyncOasisFunctions:
    """Test async OASIS functions."""

    @pytest.mark.asyncio
    async def test_collect_graph_context(self, mock_db: AsyncMock):
        """Test collect_graph_context aggregates graph data."""
        from app.services.oasis import collect_graph_context

        with patch("app.services.oasis.search_graph") as mock_search, \
             patch("app.services.oasis.get_graph_visualization") as mock_viz:
            mock_search.return_value = [{"content": "insight1"}]
            mock_viz.return_value = {"nodes": [{"label": "n1"}], "edges": [{"id": "e1"}]}

            result = await collect_graph_context("proj-1", "test focus")

            assert "insight1" in result["insights"]
            assert result["node_count"] == 1
            assert result["edge_count"] == 1

    @pytest.mark.asyncio
    async def test_generate_oasis_analysis_with_llm(self, mock_db: AsyncMock):
        """Test generate_oasis_analysis with successful LLM call."""
        from app.services.oasis import generate_oasis_analysis

        with patch("app.services.oasis.collect_graph_context") as mock_context, \
             patch("app.services.oasis.call_llm") as mock_llm, \
             patch("app.services.oasis.extract_json_object") as mock_extract:
            mock_context.return_value = {"insights": []}
            mock_llm.return_value = {"content": "response"}
            mock_extract.return_value = {
                "scenario_summary": "LLM summary",
                "key_drivers": ["driver1"],
            }

            result, context = await generate_oasis_analysis(
                project_id="proj-1",
                text="Test text",
                ontology=None,
                requirement="Test requirement",
                prompt="Test prompt",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result["scenario_summary"] == "LLM summary"

    @pytest.mark.asyncio
    async def test_generate_oasis_analysis_fallback(self, mock_db: AsyncMock):
        """Test generate_oasis_analysis falls back on LLM failure."""
        from app.services.oasis import generate_oasis_analysis

        with patch("app.services.oasis.collect_graph_context") as mock_context, \
             patch("app.services.oasis.call_llm") as mock_llm:
            mock_context.return_value = {"insights": [], "risk_signals": ["r1"]}
            mock_llm.side_effect = Exception("LLM error")

            result, context = await generate_oasis_analysis(
                project_id="proj-1",
                text="Test text",
                ontology=None,
                requirement="Test requirement",
                prompt=None,
                model=None,
                db=mock_db,
            )

            assert "fallback" in result["scenario_summary"].lower()

    @pytest.mark.asyncio
    async def test_enrich_simulation_config(self, mock_db: AsyncMock):
        """Test enrich_simulation_config."""
        from app.services.oasis import enrich_simulation_config

        analysis = {
            "scenario_summary": "Summary",
            "agent_profiles": [{"name": "Agent1"}],
        }

        with patch("app.services.oasis.call_llm") as mock_llm, \
             patch("app.services.oasis.extract_json_object") as mock_extract:
            mock_llm.return_value = {"content": "response"}
            mock_extract.return_value = {
                "active_platforms": ["twitter"],
                "time_config": {"total_hours": 48},
            }

            result = await enrich_simulation_config(
                analysis,
                requirement="Test",
                prompt="Focus",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert "twitter" in result["active_platforms"]

    @pytest.mark.asyncio
    async def test_generate_oasis_report(self, mock_db: AsyncMock):
        """Test generate_oasis_report."""
        from app.services.oasis import generate_oasis_report

        package = {"simulation_id": "sim-1"}
        analysis = {"scenario_summary": "Summary"}
        run_result = {"metrics": {"total_hours": 72}}

        with patch("app.services.oasis.call_llm") as mock_llm, \
             patch("app.services.oasis.extract_json_object") as mock_extract:
            mock_llm.return_value = {"content": "response"}
            mock_extract.return_value = {
                "title": "Test Report",
                "executive_summary": "Summary text",
                "markdown": "# Report\nContent",
            }

            result = await generate_oasis_report(
                package=package,
                analysis=analysis,
                run_result=run_result,
                requirement="Test requirement",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result["title"] == "Test Report"
            assert result["status"] == "completed"

"""Tests for OASIS simulation service functions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.oasis import (
    _as_text_list,
    _safe_agent_activity,
    _safe_agent_profiles,
    _safe_list,
    _to_float,
    _to_int,
    build_oasis_package,
    build_oasis_run_result,
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
            {"name": "Agent1", "activity_level": 0.8, "actions_per_hour": 2.5, "response_delay_minutes": 30},
            {"name": "Agent2", "activity_level": 1.5, "actions_per_hour": 25, "response_delay_minutes": 1000},
        ]
        result = _safe_agent_activity(activities)
        assert len(result) == 2
        # Check clamping
        assert result[1]["activity_level"] == 1.0  # max 1.0
        assert result[1]["actions_per_hour"] == 20.0  # max 20.0
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
        assert cfg["llm_request_timeout_seconds"] == 180
        assert cfg["llm_retry_count"] == 4
        assert cfg["llm_retry_interval_seconds"] == 2.0
        assert cfg["llm_prefer_stream"] is True
        assert cfg["llm_stream_fallback_nonstream"] is True
        assert cfg["llm_openai_api_style"] == "responses"
        assert cfg["llm_reasoning_effort"] == "model_default"
        assert cfg["llm_task_concurrency"] == 4
        assert cfg["llm_model_default_concurrency"] == 8
        assert cfg["llm_model_concurrency_overrides"] == {}
        assert cfg["graphiti_chunk_size"] == 4000
        assert cfg["graphiti_chunk_overlap"] == 160
        assert cfg["graphiti_llm_max_tokens"] == 16384

    def test_normalize_oasis_config_clamps_llm_retry(self):
        cfg = normalize_oasis_config(
            {
                "llm_request_timeout_seconds": 9999,
                "llm_retry_count": -5,
                "llm_retry_interval_seconds": 999,
                "llm_openai_api_style": "invalid",
                "llm_reasoning_effort": "invalid",
                "llm_task_concurrency": 999,
                "llm_model_default_concurrency": 0,
                "llm_model_concurrency_overrides": {"gpt-4o-mini": 999, "": 2, "bad": "x"},
                "graphiti_chunk_size": 20000,
                "graphiti_chunk_overlap": 9999,
                "graphiti_llm_max_tokens": 100,
            }
        )
        assert cfg["llm_request_timeout_seconds"] == 1800
        assert cfg["llm_retry_count"] == 0
        assert cfg["llm_retry_interval_seconds"] == 60.0
        assert cfg["llm_openai_api_style"] == "responses"
        assert cfg["llm_reasoning_effort"] == "model_default"
        assert cfg["llm_task_concurrency"] == 64
        assert cfg["llm_model_default_concurrency"] == 1
        assert cfg["llm_model_concurrency_overrides"] == {"gpt-4o-mini": 64}
        assert cfg["graphiti_chunk_size"] == 12000
        assert cfg["graphiti_chunk_overlap"] == 3000
        assert cfg["graphiti_llm_max_tokens"] == 256


class TestSanitizeOasisSimulationConfig:
    """Test sanitize_oasis_simulation_config function."""

    def test_sanitize_with_valid_data(self):
        """Test sanitize with valid configuration."""
        data = {
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
                {"name": "Agent1", "activity_level": 0.5, "actions_per_hour": 1.0, "response_delay_minutes": 60}
            ],
        }
        profiles = [{"name": "Agent1"}]
        result = sanitize_oasis_simulation_config(data, profiles)

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
            "continuation_guidance": {
                "must_follow": ["rule1"],
                "next_steps": ["step1"],
                "avoid": ["avoid1"],
            },
            "agent_profiles": [
                {
                    "name": "Agent1",
                    "role": "User",
                    "persona": "Tracks the narrative closely",
                    "stance": "neutral",
                }
            ],
        }
        graph_context = {"insights": ["i1"], "relationships": ["r1"]}
        result = sanitize_oasis_analysis(data, graph_context)

        assert result["scenario_summary"] == "Test scenario"
        assert result["continuation_guidance"]["next_steps"] == ["step1"]
        assert result["agent_profiles"][0]["name"] == "Agent1"

    def test_sanitize_analysis_with_missing_data(self):
        """Test sanitize_analysis with missing data."""
        result = sanitize_oasis_analysis({}, {})
        assert result["scenario_summary"] == ""
        assert result["continuation_guidance"]["next_steps"] == []
        assert result["agent_profiles"] == []


class TestBuildOasisPackage:
    """Test build_oasis_package function."""

    def test_build_package_with_analysis(self):
        """Test build package with existing analysis."""
        analysis = {
            "scenario_summary": "Test summary",
            "continuation_guidance": {"must_follow": ["rule1"], "next_steps": ["step1"], "avoid": []},
            "agent_profiles": [
                {
                    "name": "Agent1",
                    "role": "Analyst",
                    "persona": "Tracks narrative trends",
                    "stance": "neutral",
                    "likely_actions": ["Summarize events"],
                }
            ],
            "simulation_config": {
                "time_config": {
                    "total_hours": 48,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": "Agent1",
                        "activity_level": 0.6,
                        "actions_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
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
        assert result["simulation_requirement"] == "Test requirement"
        assert len(result["profiles"]) == 1
        
    def test_build_package_without_profiles_raises(self):
        """Test build package requires analysis-generated profiles."""
        ontology = {
            "entity_types": [
                {"name": "Person", "description": "A person"},
                {"name": "Organization", "description": "An org"},
            ]
        }
        with pytest.raises(ValueError, match="oasis_package_analysis_summary_missing"):
            build_oasis_package(
                project_id="proj-1",
                project_title="Test",
                requirement=None,
                ontology=ontology,
                analysis=None,
            )


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
                    {"name": "Agent1", "actions_per_hour": 2.0}
                ],
            },
            "profiles": [{"name": "Agent1"}],
        }
        result = build_oasis_run_result(package=package, analysis=None)

        assert result["simulation_id"] == "sim-1"
        assert result["status"] == "completed"
        assert result["metrics"]["total_hours"] == 24
        assert result["metrics"]["total_rounds"] == 24
        assert result["metrics"]["event_count"] == 1

    def test_build_run_result_with_analysis(self):
        """Test run result keeps a minimal metrics-only payload."""
        package = {"simulation_config": {}}
        analysis = {
            "risk_signals": ["risk1", "risk2"],
            "opportunity_signals": ["opp1"],
        }
        result = build_oasis_run_result(package=package, analysis=analysis)

        assert result["status"] == "completed"
        assert result["metrics"]["total_hours"] == 72
        assert "risk_signals" not in result

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

            result = await collect_graph_context("proj-1", "test focus", db=mock_db)

            assert "insight1" in result["insights"]
            assert result["node_count"] == 1
            assert result["edge_count"] == 1
            assert all(call.kwargs.get("db") is mock_db for call in mock_search.await_args_list)
            mock_viz.assert_awaited_once_with("proj-1", db=mock_db)

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
                "continuation_guidance": {
                    "must_follow": ["rule1"],
                    "next_steps": ["step1"],
                    "avoid": [],
                },
                "agent_profiles": [
                    {
                        "name": "Agent1",
                        "role": "Analyst",
                        "persona": "Tracks narrative trends",
                        "stance": "neutral",
                        "likely_actions": ["Summarize events"],
                    }
                ],
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
            assert mock_llm.await_args.kwargs["max_tokens"] == 4096
            assert mock_llm.await_args.kwargs["prefer_stream_override"] is False
            assert mock_llm.await_args.kwargs["stream_fallback_nonstream_override"] is False
            assert mock_llm.await_args.kwargs["response_schema"].__name__ == "OasisAnalysisResponse"

    @pytest.mark.asyncio
    async def test_generate_oasis_analysis_retries_on_missing_summary(self, mock_db: AsyncMock):
        from app.services.oasis import generate_oasis_analysis

        with patch("app.services.oasis.collect_graph_context") as mock_context, \
             patch("app.services.oasis.call_llm") as mock_llm, \
             patch("app.services.oasis.extract_json_object") as mock_extract:
            mock_context.return_value = {
                "insights": [],
                "relationships": ["Agent1 influences Agent2"],
                "top_nodes": [{"label": "Agent1"}, {"label": "Agent2"}],
            }
            mock_llm.side_effect = [{"content": "first"}, {"content": "second"}]
            mock_extract.side_effect = [
                {
                    "scenario_summary": "",
                    "continuation_guidance": {
                        "must_follow": ["rule1"],
                        "next_steps": ["step1"],
                        "avoid": [],
                    },
                    "agent_profiles": [
                        {
                            "name": "Agent1",
                            "role": "Analyst",
                            "persona": "Tracks narrative trends",
                            "stance": "neutral",
                            "likely_actions": ["Summarize events"],
                        }
                    ],
                },
                {
                    "scenario_summary": "Recovered summary",
                    "continuation_guidance": {
                        "must_follow": ["rule1"],
                        "next_steps": ["step1"],
                        "avoid": [],
                    },
                    "agent_profiles": [
                        {
                            "name": "Agent1",
                            "role": "Analyst",
                            "persona": "Tracks narrative trends",
                            "stance": "neutral",
                            "likely_actions": ["Summarize events"],
                        }
                    ],
                },
            ]

            result, _ = await generate_oasis_analysis(
                project_id="proj-1",
                text="Test text",
                ontology=None,
                requirement="Test requirement",
                prompt="Test prompt",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result["scenario_summary"] == "Recovered summary"
            assert mock_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_generate_oasis_analysis_retries_on_validation_error(self, mock_db: AsyncMock):
        from app.services.oasis import generate_oasis_analysis

        with patch("app.services.oasis.collect_graph_context") as mock_context,              patch("app.services.oasis.call_llm") as mock_llm,              patch("app.services.oasis.extract_json_object") as mock_extract:
            mock_context.return_value = {"insights": []}
            mock_llm.side_effect = [
                {"content": "first"},
                {"content": "second"},
            ]
            mock_extract.side_effect = [
                {
                    "scenario_summary": "First summary",
                    "continuation_guidance": {
                        "must_follow": ["rule1"],
                        "next_steps": ["step1"],
                        "avoid": [],
                    },
                    "agent_profiles": [],
                },
                {
                    "scenario_summary": "Recovered summary",
                    "continuation_guidance": {
                        "must_follow": ["rule1"],
                        "next_steps": ["step1"],
                        "avoid": [],
                    },
                    "agent_profiles": [
                        {
                            "name": "Agent1",
                            "role": "Analyst",
                            "persona": "Tracks narrative trends",
                            "stance": "neutral",
                            "likely_actions": ["Summarize events"],
                        }
                    ],
                },
            ]

            result, _ = await generate_oasis_analysis(
                project_id="proj-1",
                text="Test text",
                ontology=None,
                requirement="Test requirement",
                prompt="Test prompt",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result["scenario_summary"] == "Recovered summary"
            assert mock_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_generate_oasis_analysis_invalid_top_level_json_retries(self, mock_db: AsyncMock):
        from app.services.oasis import generate_oasis_analysis

        with patch("app.services.oasis.collect_graph_context") as mock_context,              patch("app.services.oasis.call_llm") as mock_llm,              patch("app.services.oasis.extract_json_object") as mock_extract:
            mock_context.return_value = {"insights": []}
            mock_llm.side_effect = [{"content": "invalid"}, {"content": "valid"}]
            mock_extract.side_effect = [
                None,
                {
                    "scenario_summary": "Recovered summary",
                    "continuation_guidance": {
                        "must_follow": ["rule1"],
                        "next_steps": ["step1"],
                        "avoid": [],
                    },
                    "agent_profiles": [
                        {
                            "name": "Agent1",
                            "role": "Analyst",
                            "persona": "Tracks narrative trends",
                            "stance": "neutral",
                            "likely_actions": ["Summarize events"],
                        }
                    ],
                },
            ]

            result, _ = await generate_oasis_analysis(
                project_id="proj-1",
                text="Test text",
                ontology=None,
                requirement="Test requirement",
                prompt="Test prompt",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result["scenario_summary"] == "Recovered summary"
            assert result["continuation_guidance"]["next_steps"] == ["step1"]
            assert mock_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_generate_oasis_analysis_failure_raises(self, mock_db: AsyncMock):
        """Test generate_oasis_analysis raises on LLM failure."""
        from app.services.oasis import generate_oasis_analysis

        with patch("app.services.oasis.collect_graph_context") as mock_context, \
             patch("app.services.oasis.call_llm") as mock_llm:
            mock_context.return_value = {"insights": [], "risk_signals": ["r1"]}
            mock_llm.side_effect = Exception("LLM error")

            with pytest.raises(Exception, match="LLM error"):
                await generate_oasis_analysis(
                    project_id="proj-1",
                    text="Test text",
                    ontology=None,
                    requirement="Test requirement",
                    prompt=None,
                    model=None,
                    db=mock_db,
                )

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
                "time_config": {
                    "total_hours": 48,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": "Agent1",
                        "activity_level": 0.6,
                        "actions_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            }

            result = await enrich_simulation_config(
                analysis,
                requirement="Test",
                prompt="Focus",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result["agent_activity"][0]["actions_per_hour"] == 1.0
            assert mock_llm.await_args.kwargs["max_tokens"] == 2048
            assert mock_llm.await_args.kwargs["prefer_stream_override"] is False
            assert mock_llm.await_args.kwargs["stream_fallback_nonstream_override"] is False
            assert mock_llm.await_args.kwargs["response_schema"].__name__ == "OasisSimulationConfigResponse"

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
                "key_findings": ["finding1"],
                "next_actions": ["action1"],
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
            assert mock_llm.await_args.kwargs["prefer_stream_override"] is False
            assert mock_llm.await_args.kwargs["stream_fallback_nonstream_override"] is False
            assert mock_llm.await_args.kwargs["response_schema"].__name__ == "OasisReportResponse"

    @pytest.mark.asyncio
    async def test_generate_oasis_report_invalid_top_level_json_retries(self, mock_db: AsyncMock):
        """Test generate_oasis_report retries when top-level JSON is invalid."""
        from app.services.oasis import generate_oasis_report

        package = {"simulation_id": "sim-1"}
        analysis = {"scenario_summary": "Summary"}
        run_result = {"metrics": {"total_hours": 72}}

        with patch(
            "app.services.oasis.call_llm",
            new=AsyncMock(side_effect=[{"content": "invalid"}, {"content": "valid"}]),
        ), patch(
            "app.services.oasis.extract_json_object",
            side_effect=[
                None,
                {
                    "title": "Recovered Report",
                    "executive_summary": "Recovered summary",
                    "key_findings": ["finding1"],
                    "next_actions": ["action1"],
                    "markdown": "# Report\nRecovered",
                },
            ],
        ):
            result = await generate_oasis_report(
                package=package,
                analysis=analysis,
                run_result=run_result,
                requirement="Test requirement",
                model="gpt-4o-mini",
                db=mock_db,
            )

            assert result["title"] == "Recovered Report"
            assert result["executive_summary"] == "Recovered summary"
            assert result["key_findings"] == ["finding1"]
            assert result["next_actions"] == ["action1"]

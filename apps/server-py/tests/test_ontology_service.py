"""Tests for ontology service functions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOntologyService:
    """Test ontology service functions."""

    def test_normalize_name_basic(self):
        """Test normalizing entity/relation names."""
        from app.services.ontology import _normalize_name

        result = _normalize_name("Person Type")
        assert result == "PERSON_TYPE"

    def test_normalize_name_with_special_chars(self):
        """Test normalizing names with special characters."""
        from app.services.ontology import _normalize_name

        result = _normalize_name("test-entity@name!")
        assert "TEST" in result or "ENTITY" in result

    def test_normalize_name_empty(self):
        """Test normalizing empty name stays empty."""
        from app.services.ontology import _normalize_name

        result = _normalize_name("")
        assert result == ""

    def test_normalize_name_none(self):
        """Test normalizing None stays empty."""
        from app.services.ontology import _normalize_name

        result = _normalize_name(None)
        assert result == ""

    def test_sanitize_ontology_basic(self):
        """Test sanitizing ontology data."""
        from app.services.ontology import _sanitize_ontology

        data = {
            "entity_types": [{"name": "Person", "description": "A person"}],
            "edge_types": [{"name": "KNOWS", "source_type": "Person", "target_type": "Person"}],
        }

        result = _sanitize_ontology(data)
        assert "entity_types" in result
        assert "edge_types" in result
        assert len(result["entity_types"]) == 1
        assert result["entity_types"][0]["name"] == "PERSON"

    def test_sanitize_ontology_empty(self):
        """Test sanitizing empty ontology keeps empty lists."""
        from app.services.ontology import _sanitize_ontology

        result = _sanitize_ontology({})
        assert "entity_types" in result
        assert "edge_types" in result
        assert result["entity_types"] == []
        assert result["edge_types"] == []

    def test_sanitize_ontology_preserves_memory_dimensions(self):
        """Test sanitizing keeps project-specific memory lanes."""
        from app.services.ontology import _sanitize_ontology

        data = {
            "memory_dimensions": [
                {"name": "Character State", "description": "Current role, secrets, motivation."},
                {"name": "Character State", "description": "duplicate"},
                {"name": "Open Thread", "description": "Unresolved promise or setup."},
            ],
            "entity_types": [],
            "edge_types": [],
        }

        result = _sanitize_ontology(data)

        assert result["memory_dimensions"] == [
            {"name": "character_state", "description": "Current role, secrets, motivation."},
            {"name": "open_thread", "description": "Unresolved promise or setup."},
        ]

    def test_sanitize_ontology_deduplicates(self):
        """Test sanitizing deduplicates entity names."""
        from app.services.ontology import _sanitize_ontology

        data = {
            "entity_types": [
                {"name": "Person", "description": "First"},
                {"name": "Person", "description": "Duplicate"},
            ],
            "edge_types": [],
        }

        result = _sanitize_ontology(data)
        assert len(result["entity_types"]) == 1

    def test_sanitize_ontology_filters_edges_outside_entity_limit(self):
        """Test edge source/target references stay within retained entity types."""
        from app.services.ontology import _sanitize_ontology

        data = {
            "entity_types": [
                {"name": f"Entity {index}", "description": "entity"}
                for index in range(1, 30)
            ],
            "edge_types": [
                {"name": "VALID_EDGE", "source_type": "Entity 1", "target_type": "Entity 2"},
                {"name": "INVALID_EDGE", "source_type": "Entity 1", "target_type": "Entity 29"},
            ],
        }

        result = _sanitize_ontology(data)

        assert len(result["entity_types"]) == 24
        assert [edge["name"] for edge in result["edge_types"]] == ["VALID_EDGE"]

    def test_build_ontology_source_excerpt_respects_budget(self):
        """Test ontology excerpt keeps long content within prompt budget."""
        from app.services.ontology import _build_ontology_source_excerpt

        text = "\n\n".join(
            f"Section {index}: " + ("Mira repaired the tide engine. " * 120)
            for index in range(1, 9)
        )

        result = _build_ontology_source_excerpt(text, max_chars=8000)

        assert len(result) <= 8000
        assert "Section 1" in result
        assert result != text
        assert "[...]" in result

    def test_build_ontology_prompt_uses_50000_character_excerpt(self, monkeypatch: pytest.MonkeyPatch):
        """Test ontology prompt includes the expanded analysis excerpt budget."""
        from app.services import ontology

        called: dict[str, int] = {}
        monkeypatch.setattr(
            ontology,
            "_build_ontology_source_excerpt",
            lambda _text, *, max_chars: called.setdefault("max_chars", max_chars) and "sample",
        )

        ontology._build_ontology_prompt("source", None)

        assert called["max_chars"] == 50000

    @pytest.mark.asyncio
    async def test_generate_ontology_empty_text(self):
        """Test generating ontology with empty text raises ValueError."""
        from app.services.ontology import generate_ontology

        mock_db = AsyncMock()

        with pytest.raises(ValueError, match="No source text provided"):
            await generate_ontology(
                text="",
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_generate_ontology_with_text(self):
        """Test generating ontology with text."""
        from app.services.ontology import generate_ontology

        mock_db = AsyncMock()

        # Mock the database query for AI providers
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.services.ontology.call_llm") as mock_llm:
            mock_llm.return_value = {
                "content": '{"text_type": "fiction", "text_type_confidence": 0.8, "text_type_reason": "Named characters and interpersonal action.", "memory_dimensions": [{"name": "character_state", "description": "Current character facts."}], "entity_types": [{"name": "Person", "description": "A person"}], "edge_types": [{"name": "KNOWS", "source_type": "Person", "target_type": "Person"}], "analysis_summary": "Test"}'
            }

            result = await generate_ontology(
                text="John knows Mary.",
                db=mock_db,
                model="gpt-4o-mini",
            )

            assert result is not None
            assert "entity_types" in result
            assert result["memory_dimensions"][0]["name"] == "character_state"
            assert result["text_type"] == "fiction"
            assert result["text_type_confidence"] == 0.8
            assert mock_llm.await_args_list[0].kwargs["prefer_stream_override"] is True
            assert mock_llm.await_args_list[0].kwargs["max_tokens"] == 4096
            assert mock_llm.await_args_list[0].kwargs["minimum_timeout_seconds"] == 300
            assert mock_llm.await_args_list[0].kwargs["response_schema"].__name__ == "OntologyResponse"

    @pytest.mark.asyncio
    async def test_generate_ontology_llm_failure_raises_runtime_error(self):
        """Test that LLM failure raises explicit pipeline error."""
        from app.services.ontology import generate_ontology

        mock_db = AsyncMock()

        # Mock the database query for AI providers
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.services.ontology.call_llm") as mock_llm:
            mock_llm.side_effect = Exception("LLM error")

            with pytest.raises(RuntimeError, match="ontology_pipeline_failed:Exception:LLM error"):
                await generate_ontology(
                    text="Some text to analyze",
                    db=mock_db,
                    model="gpt-4o-mini",
                )

    @pytest.mark.asyncio
    async def test_generate_ontology_retries_when_edge_types_are_missing(self):
        """Test invalid ontology content triggers a retry instead of internal repair."""
        from app.services.ontology import generate_ontology

        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.services.ontology.call_llm") as mock_llm:
            mock_llm.side_effect = [
                {
                    "content": '{"text_type": "business", "text_type_confidence": 0.7, "text_type_reason": "Organization relationship.", "memory_dimensions": [{"name": "stakeholder_state", "description": "Known stakeholder facts."}], "entity_types": [{"name": "Person"}, {"name": "Organization"}], "edge_types": [{"name": "works_for"}], "analysis_summary": "ok"}'
                },
                {
                    "content": '{"text_type": "business", "text_type_confidence": 0.9, "text_type_reason": "Employment relation between person and company.", "memory_dimensions": [{"name": "stakeholder_state", "description": "Known stakeholder facts."}], "entity_types": [{"name": "Person"}, {"name": "Organization"}], "edge_types": [{"name": "works_for", "source_type": "Person", "target_type": "Organization"}], "analysis_summary": "ok"}'
                },
            ]

            result = await generate_ontology(
                text="Tom works for Acme.",
                db=mock_db,
                model="gpt-4o-mini",
            )

            assert result["edge_types"][0]["name"] == "WORKS_FOR"
            assert result["edge_types"][0]["source_type"] == "PERSON"
            assert result["edge_types"][0]["target_type"] == "ORGANIZATION"
            assert result["text_type"] == "business"
            assert mock_llm.await_count == 2
            assert mock_llm.await_args_list[0].kwargs["prefer_stream_override"] is True
            assert mock_llm.await_args_list[1].kwargs["max_tokens"] == 4096
            assert mock_llm.await_args_list[1].kwargs["minimum_timeout_seconds"] == 300
            assert mock_llm.await_args_list[0].kwargs["response_schema"].__name__ == "OntologyResponse"

    @pytest.mark.asyncio
    async def test_generate_ontology_invalid_json_raises(self):
        """Test invalid JSON response raises strict validation error."""
        from app.services.ontology import generate_ontology

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.services.ontology.call_llm") as mock_llm:
            mock_llm.return_value = {"content": "not json"}

            with pytest.raises(ValueError, match="llm_response_not_json_or_invalid_schema"):
                await generate_ontology(
                    text="Tom works for Acme.",
                    db=mock_db,
                    model="gpt-4o-mini",
                )

    def test_build_memory_input_with_ontology_none(self):
        """Test building memory input with None ontology."""
        from app.services.ontology import build_memory_input_with_ontology

        result = build_memory_input_with_ontology("Test text", None)
        assert result == "Test text"

    def test_build_memory_input_with_ontology_valid(self):
        """Test building memory input with valid ontology."""
        from app.services.ontology import build_memory_input_with_ontology

        ontology = {
            "entity_types": [{"name": "Person", "description": "A person"}],
            "edge_types": [{"name": "KNOWS", "source_type": "Person", "target_type": "Person"}],
        }

        result = build_memory_input_with_ontology("Test text", ontology)
        assert "[ONTOLOGY_CONTEXT]" in result
        assert "Test text" in result

    def test_build_memory_input_with_ontology_invalid(self):
        """Test building memory input with invalid ontology returns text."""
        from app.services.ontology import build_memory_input_with_ontology

        result = build_memory_input_with_ontology("Test text", {"invalid": "data"})
        assert "Test text" in result

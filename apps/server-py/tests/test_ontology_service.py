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
        """Test normalizing empty name returns default."""
        from app.services.ontology import _normalize_name

        result = _normalize_name("")
        assert result == "CONCEPT"

    def test_normalize_name_none(self):
        """Test normalizing None returns default."""
        from app.services.ontology import _normalize_name

        result = _normalize_name(None)
        assert result == "CONCEPT"

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
                "content": '{"entity_types": [{"name": "Person", "description": "A person"}], "edge_types": [{"name": "KNOWS", "source_type": "Person", "target_type": "Person"}], "analysis_summary": "Test"}'
            }

            result = await generate_ontology(
                text="John knows Mary.",
                db=mock_db,
            )

            assert result is not None
            assert "entity_types" in result
            assert mock_llm.await_args_list[0].kwargs["prefer_stream_override"] is False
            assert mock_llm.await_args_list[0].kwargs["stream_fallback_nonstream_override"] is False

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
                )

    @pytest.mark.asyncio
    async def test_generate_ontology_infers_edge_types_when_missing(self):
        """Test missing edge source/target types are inferred from entities."""
        from app.services.ontology import generate_ontology

        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.services.ontology.call_llm") as mock_llm:
            mock_llm.return_value = {
                "content": '{"entity_types": [{"name": "Person"}, {"name": "Organization"}], "edge_types": [{"name": "works_for"}], "analysis_summary": "ok"}'
            }

            result = await generate_ontology(
                text="Tom works for Acme.",
                db=mock_db,
            )

            assert result["edge_types"][0]["name"] == "WORKS_FOR"
            assert result["edge_types"][0]["source_type"] == "PERSON"
            assert result["edge_types"][0]["target_type"] == "ORGANIZATION"
            assert mock_llm.await_args_list[0].kwargs["prefer_stream_override"] is False
            assert mock_llm.await_args_list[0].kwargs["stream_fallback_nonstream_override"] is False

    @pytest.mark.asyncio
    async def test_generate_ontology_invalid_json_raises(self):
        """Test invalid JSON response raises strict validation error."""
        from app.services.ontology import generate_ontology

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.services.ontology.call_llm") as mock_llm, \
             patch("app.services.ontology._repair_ontology_json", new_callable=AsyncMock, return_value=None):
            mock_llm.return_value = {"content": "not json"}

            with pytest.raises(ValueError, match="llm_response_not_json_or_invalid_schema_after_repair"):
                await generate_ontology(
                    text="Tom works for Acme.",
                    db=mock_db,
                )

    def test_build_graph_input_with_ontology_none(self):
        """Test building graph input with None ontology."""
        from app.services.ontology import build_graph_input_with_ontology

        result = build_graph_input_with_ontology("Test text", None)
        assert result == "Test text"

    def test_build_graph_input_with_ontology_valid(self):
        """Test building graph input with valid ontology."""
        from app.services.ontology import build_graph_input_with_ontology

        ontology = {
            "entity_types": [{"name": "Person", "description": "A person"}],
            "edge_types": [{"name": "KNOWS", "source_type": "Person", "target_type": "Person"}],
        }

        result = build_graph_input_with_ontology("Test text", ontology)
        assert "[ONTOLOGY_CONTEXT]" in result
        assert "Test text" in result

    def test_build_graph_input_with_ontology_invalid(self):
        """Test building graph input with invalid ontology returns text."""
        from app.services.ontology import build_graph_input_with_ontology

        result = build_graph_input_with_ontology("Test text", {"invalid": "data"})
        assert "Test text" in result

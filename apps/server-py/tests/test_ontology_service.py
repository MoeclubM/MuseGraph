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

    def test_fallback_ontology_basic(self):
        """Test fallback ontology generation."""
        from app.services.ontology import _fallback_ontology

        result = _fallback_ontology("John works at Microsoft")
        assert "entity_types" in result
        assert "edge_types" in result
        assert "analysis_summary" in result

    def test_fallback_ontology_empty_text(self):
        """Test fallback ontology with empty text."""
        from app.services.ontology import _fallback_ontology

        result = _fallback_ontology("")
        assert "entity_types" in result
        assert len(result["entity_types"]) >= 1

    def test_fallback_ontology_with_requirement(self):
        """Test fallback ontology includes requirement."""
        from app.services.ontology import _fallback_ontology

        result = _fallback_ontology("Test text", "Custom requirement")
        assert "Custom requirement" in result["analysis_summary"]

    def test_fallback_ontology_detects_person(self):
        """Test fallback contains character-like entity type."""
        from app.services.ontology import _fallback_ontology

        result = _fallback_ontology("He went to the store. She stayed home.")
        entity_names = [e["name"] for e in result["entity_types"]]
        assert "CHARACTER" in entity_names

    def test_fallback_ontology_detects_organization(self):
        """Test fallback detects organization keywords."""
        from app.services.ontology import _fallback_ontology

        result = _fallback_ontology("The company announced a new product. The team worked hard.")
        entity_names = [e["name"] for e in result["entity_types"]]
        assert "ORGANIZATION" in entity_names

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

    @pytest.mark.asyncio
    async def test_generate_ontology_llm_failure_returns_fallback(self):
        """Test that LLM failure returns fallback ontology."""
        from app.services.ontology import generate_ontology

        mock_db = AsyncMock()

        # Mock the database query for AI providers
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.services.ontology.call_llm") as mock_llm:
            mock_llm.side_effect = Exception("LLM error")

            result = await generate_ontology(
                text="Some text to analyze",
                db=mock_db,
            )

            assert result is not None
            assert "entity_types" in result
            # Should be fallback ontology
            assert result["entity_types"][0]["name"] == "CHARACTER"
            assert str(result.get("_meta", {}).get("fallback_reason") or "").startswith("ontology_pipeline_failed")

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
            assert result.get("_meta", {}).get("fallback_reason") is None

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

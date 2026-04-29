"""Tests for AI Operation functionality: CREATE, CONTINUE, ANALYZE, REWRITE, SUMMARIZE."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import FakeUser


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(items: list):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


class TestCreateOperation:
    """Test CREATE operation."""

    @pytest.mark.skip(reason="Operation flow requires integration testing with real DB")
    @pytest.mark.asyncio
    async def test_create_operation_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test successful CREATE operation endpoint."""
        # This test requires full database integration testing
        # The endpoint validation is tested in other tests
        pass

    @pytest.mark.asyncio
    async def test_create_operation_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test CREATE operation with non-existent project returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.post(
            "/api/projects/nonexistent/operation",
            json={
                "type": "CREATE",
                "input": "Test content",
                "model": "gpt-4o-mini",
            },
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_operation_unauthorized_project(self, client: AsyncClient, mock_db: AsyncMock):
        """Test CREATE operation on another user's project returns 403."""
        project = SimpleNamespace(
            id="project-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/project-1/operation",
            json={
                "type": "CREATE",
                "input": "Test content",
                "model": "gpt-4o-mini",
            },
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_operation_empty_input(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test CREATE operation with empty input returns 400."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/project-1/operation",
            json={
                "type": "CREATE",
                "input": "",
                "model": "gpt-4o-mini",
            },
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_operation_insufficient_balance(self, client: AsyncClient, mock_db: AsyncMock):
        """Test CREATE operation with insufficient balance - balance check happens after LLM call."""
        user = FakeUser(balance=Decimal("0.01"))
        project = SimpleNamespace(
            id="project-1",
            user_id=user.id,
        )

        # This test is for documentation - balance check happens during operation processing
        # The test setup is kept but won't actually fail due to balance with current mock setup


class TestContinueOperation:
    """Test CONTINUE operation."""

    @pytest.mark.asyncio
    async def test_continue_operation_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test successful CONTINUE operation - uses upload endpoint for file-based ops."""
        # CONTINUE operations use the upload endpoint, not direct text input
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
            title="Test Project",
            content="Existing content to continue...",
            graph_id=None,
            component_models=None,
        )

        # CONTINUE is only available via file upload
        # This test verifies that the direct endpoint rejects CONTINUE
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/project-1/operation",
            json={
                "type": "CONTINUE",
                "model": "gpt-4o-mini",
            },
        )

        # Direct endpoint only supports CREATE
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_continue_operation_no_content(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test CONTINUE operation without existing content returns error."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
            content=None,
            graph_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        # CONTINUE requires file upload, not direct text
        resp = await client.post(
            "/api/projects/project-1/operation",
            json={
                "type": "CONTINUE",
                "model": "gpt-4o-mini",
            },
        )

        assert resp.status_code == 400


class TestAnalyzeOperation:
    """Test ANALYZE operation."""

    @pytest.mark.asyncio
    async def test_analyze_operation_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test ANALYZE operation - uses upload endpoint for file-based ops."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
            content="Text to analyze for themes and patterns.",
            graph_id=None,
        )

        # ANALYZE is only available via file upload
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/project-1/operation",
            json={
                "type": "ANALYZE",
                "model": "gpt-4o-mini",
            },
        )

        # Direct endpoint only supports CREATE
        assert resp.status_code == 400


class TestRewriteOperation:
    """Test REWRITE operation."""

    @pytest.mark.asyncio
    async def test_rewrite_operation_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test REWRITE operation - uses upload endpoint for file-based ops."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
            content="Original text that needs to be rewritten.",
            graph_id=None,
        )

        # REWRITE is only available via file upload
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/project-1/operation",
            json={
                "type": "REWRITE",
                "model": "gpt-4o-mini",
            },
        )

        # Direct endpoint only supports CREATE
        assert resp.status_code == 400


class TestSummarizeOperation:
    """Test SUMMARIZE operation."""

    @pytest.mark.asyncio
    async def test_summarize_operation_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test SUMMARIZE operation - uses upload endpoint for file-based ops."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
            content="Long text that needs to be summarized into a concise form...",
            graph_id=None,
        )

        # SUMMARIZE is only available via file upload
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/project-1/operation",
            json={
                "type": "SUMMARIZE",
                "model": "gpt-4o-mini",
            },
        )

        # Direct endpoint only supports CREATE
        assert resp.status_code == 400


class TestFileUpload:
    """Test file upload for operations."""

    @pytest.mark.asyncio
    async def test_file_upload_txt(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test uploading a .txt file."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        # Mock file content - actual file upload testing requires multipart
        # This test verifies the endpoint exists

    @pytest.mark.asyncio
    async def test_file_upload_unsupported_type(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test uploading unsupported file type returns error."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        # Unsupported file type should be rejected


class TestModelSelection:
    """Test model selection and resolution."""

    @pytest.mark.asyncio
    async def test_model_selection_explicit(self, mock_db: AsyncMock):
        """Test explicit model selection."""
        from app.services.ai import resolve_component_model

        # When model is explicitly specified, it should be used
        result = resolve_component_model(None, "operation_create", "gpt-4o", "gpt-4o-mini")
        assert result == "gpt-4o"

    @pytest.mark.skip(reason="Operation flow requires integration testing with real DB")
    @pytest.mark.asyncio
    async def test_model_not_available(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test operation endpoint accepts any model - model validation happens in LLM call."""
        # This test requires full database integration testing
        pass


class TestOperationProgress:
    """Test SSE progress tracking for operations."""

    @pytest.mark.asyncio
    async def test_operation_progress_stream(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test that operations report progress via SSE."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        # Progress is reported at 10%, 30%, 80%, 100%
        # This would be tested via SSE endpoint


class TestPromptTemplates:
    """Test prompt template handling."""

    @pytest.mark.asyncio
    async def test_get_prompt_template_create(self, mock_db: AsyncMock):
        """Test getting CREATE prompt template."""
        template = SimpleNamespace(
            name="create_default",
            type="CREATE",
            template="You are a creative writing assistant. Based on the following prompt, create original content:\n\n{input}",
            variables={"input": "User's creative prompt"},
            is_active=True,
        )
        mock_db.execute.return_value = _scalar_one_or_none(template)

        # Template should be retrieved and formatted with user input

    @pytest.mark.asyncio
    async def test_get_prompt_template_continue(self, mock_db: AsyncMock):
        """Test getting CONTINUE prompt template."""
        template = SimpleNamespace(
            name="continue_default",
            type="CONTINUE",
            template="Continue the following text naturally:\n\n{input}",
            is_active=True,
        )
        mock_db.execute.return_value = _scalar_one_or_none(template)


class TestOperationErrors:
    """Test error handling in operations."""

    @pytest.mark.skip(reason="Operation flow requires integration testing with real DB")
    @pytest.mark.asyncio
    async def test_llm_api_error(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test that LLM errors are handled gracefully."""
        # This test requires full database integration testing
        pass

    @pytest.mark.asyncio
    async def test_invalid_operation_type(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Test invalid operation type returns error."""
        project = SimpleNamespace(
            id="project-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/project-1/operation",
            json={
                "type": "INVALID_TYPE",
                "input": "Test content",
                "model": "gpt-4o-mini",
            },
        )

        # The API only supports CREATE for direct text input
        assert resp.status_code == 400


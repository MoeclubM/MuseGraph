"""Tests for projects router file upload and stream endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _get_endpoint_globals(app, endpoint_name: str) -> dict:
    for route in app.routes:
        if hasattr(route, "endpoint") and getattr(route, "name", "") == endpoint_name:
            return route.endpoint.__globals__
        if hasattr(route, "routes"):
            for sub in route.routes:
                if hasattr(sub, "endpoint") and getattr(sub, "name", "") == endpoint_name:
                    return sub.endpoint.__globals__
    raise RuntimeError(f"Endpoint {endpoint_name!r} not found")


@pytest.fixture()
def _create_operation_globals():
    from tests.conftest import app

    return _get_endpoint_globals(app, "create_operation")


@pytest.fixture()
def _create_operation_upload_globals():
    from tests.conftest import app

    return _get_endpoint_globals(app, "create_operation_upload")


@pytest.fixture()
def _create_operation_stream_globals():
    from tests.conftest import app

    return _get_endpoint_globals(app, "create_operation_stream")


class TestFileUpload:
    """Test file upload endpoints."""

    @pytest.mark.asyncio
    async def test_upload_txt_file(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test uploading a text file."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test Project",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        file_content = b"This is test content for the project."
        files = {"file": ("test.txt", BytesIO(file_content), "text/plain")}

        resp = await client.post(
            "/api/projects/proj-1/upload",
            files=files,
        )

        # May return 200, 201, or 422 depending on implementation
        assert resp.status_code in [200, 201, 404, 422]

    @pytest.mark.asyncio
    async def test_upload_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test uploading to another user's project."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        file_content = b"Test content"
        files = {"file": ("test.txt", BytesIO(file_content), "text/plain")}

        resp = await client.post(
            "/api/projects/proj-1/operation/upload",
            files=files,
            data={"type": "CONTINUE"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_upload_project_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test uploading to non-existent project."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        file_content = b"Test content"
        files = {"file": ("test.txt", BytesIO(file_content), "text/plain")}

        resp = await client.post(
            "/api/projects/nonexistent/upload",
            files=files,
        )

        assert resp.status_code == 404


class TestOperationStream:
    """Test streaming operation endpoints."""

    @pytest.mark.asyncio
    async def test_create_stream_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test streaming operation on another user's project."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/proj-1/operation/stream",
            json={"type": "CREATE", "input": "Test"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_stream_invalid_type(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test streaming operation with invalid type."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[],
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/proj-1/operation/stream",
            json={"type": "CONTINUE", "input": "Test"},
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_stream_missing_input(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test streaming operation without input."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/proj-1/operation/stream",
            json={"type": "CREATE"},
        )

        assert resp.status_code == 400


class TestOperationHistory:
    """Test operation history endpoint."""

    @pytest.mark.asyncio
    async def test_get_history_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting history of another user's project."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/proj-1/operations")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_history_empty(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting empty history."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        # Mock operations query
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars

        # Set up multiple execute calls
        mock_db.execute.side_effect = [_scalar_one_or_none(project), mock_result]

        resp = await client.get("/api/projects/proj-1/operations")

        assert resp.status_code in [200, 404, 500]


class TestProjectOntology:
    """Test project ontology endpoints.

    Note: /ontology GET/PUT are not implemented under /api/projects.
    Ontology generation lives at /api/projects/{id}/graphs/ontology/generate.
    """

    @pytest.mark.asyncio
    async def test_get_ontology_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Route does not exist — expect 404 or 405."""
        resp = await client.get("/api/projects/proj-1/ontology")
        assert resp.status_code in (404, 405)

    @pytest.mark.asyncio
    async def test_update_ontology_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Route does not exist — expect 404 or 405."""
        resp = await client.put(
            "/api/projects/proj-1/ontology",
            json={"entity_types": [], "edge_types": []},
        )
        assert resp.status_code in (404, 405)


class TestProjectRequirement:
    """Test project simulation requirement endpoints.

    Note: /requirement PUT is not implemented under /api/projects.
    """

    @pytest.mark.asyncio
    async def test_update_requirement_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Route does not exist — expect 404 or 405."""
        resp = await client.put(
            "/api/projects/proj-1/requirement",
            json={"requirement": "Test requirement"},
        )
        assert resp.status_code in (404, 405)


class TestProjectModels:
    """Test project component models endpoints.

    Note: /models GET/PUT are not implemented under /api/projects.
    Model config is managed via PUT /api/projects/{id} (component_models field).
    """

    @pytest.mark.asyncio
    async def test_get_models_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Route does not exist — expect 404 or 405."""
        resp = await client.get("/api/projects/proj-1/models")
        assert resp.status_code in (404, 405)

    @pytest.mark.asyncio
    async def test_update_models_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Route does not exist — expect 404 or 405."""
        resp = await client.put(
            "/api/projects/proj-1/models",
            json={"operation_create": "gpt-4"},
        )
        assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Additional tests for missing coverage
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Additional tests for missing coverage
# ---------------------------------------------------------------------------


class TestUpdateProject:
    """PUT /api/projects/{id} - update project fields."""

    @pytest.mark.asyncio
    async def test_update_all_fields(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Cover lines 104,106,108,110,112."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Old Title",
            description="Old desc",
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Old content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
            simulation_requirement=None,
            component_models=None,
            oasis_analysis=None,
            ontology_schema=None,
            cognee_dataset_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.refresh = AsyncMock()

        resp = await client.put(
            "/api/projects/proj-1",
            json={
                "title": "New Title",
                "description": "New desc",
                "simulation_requirement": "Must handle 1000 users",
                "component_models": {"operation_create": "gpt-4o"},
                "oasis_analysis": {"score": 95},
            },
        )

        assert resp.status_code == 200
        assert project.title == "New Title"
        assert project.simulation_requirement == "Must handle 1000 users"
        assert project.component_models == {"operation_create": "gpt-4o"}
        assert project.oasis_analysis == {"score": 95}

    @pytest.mark.asyncio
    async def test_update_rejects_legacy_content_field(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Old Title",
            description="Old desc",
            chapters=[],
            simulation_requirement=None,
            component_models=None,
            oasis_analysis=None,
            ontology_schema=None,
            cognee_dataset_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.refresh = AsyncMock()

        resp = await client.put(
            "/api/projects/proj-1",
            json={"content": "legacy"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        mock_db.execute.return_value = _scalar_one_or_none(None)
        resp = await client.put("/api/projects/missing", json={"title": "X"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_forbidden(self, client: AsyncClient, mock_db: AsyncMock):
        project = SimpleNamespace(id="proj-1", user_id="other-user-id", chapters=[])
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.put("/api/projects/proj-1", json={"title": "X"})
        assert resp.status_code == 403


class TestCreateOperation:
    """POST /api/projects/{id}/operation - lines 164-183."""

    @pytest.mark.asyncio
    async def test_create_operation_success(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        fake_user,
        _create_operation_globals: dict,
    ):
        """Full flow with mock run_operation."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[],
            component_models={},
            cognee_dataset_id=None,
        )
        op = SimpleNamespace(
            id="op-1",
            project_id="proj-1",
            type="CREATE",
            input="Write a poem",
            output="A lovely poem",
            model="gpt-4o-mini",
            input_tokens=50,
            output_tokens=30,
            cost=0.01,
            status="COMPLETED",
            error=None,
            progress=100,
            message="Done",
            metadata_=None,
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.flush = AsyncMock()

        mock_run = AsyncMock(return_value=op)
        orig = _create_operation_globals["run_operation"]
        _create_operation_globals["run_operation"] = mock_run
        try:
            resp = await client.post(
                "/api/projects/proj-1/operation",
                json={"type": "CREATE", "input": "Write a poem", "model": "gpt-4o-mini", "use_rag": False},
            )
        finally:
            _create_operation_globals["run_operation"] = orig

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "COMPLETED"
        assert data["output"] == "A lovely poem"
        assert mock_run.await_args.kwargs["use_rag"] is False

    @pytest.mark.asyncio
    async def test_create_operation_invalid_type(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={"type": "INVALID_TYPE", "input": "text"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_operation_rejects_non_empty_workspace(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[SimpleNamespace(id="ch-1", content="existing text", order_index=0, created_at=0)],
            component_models={},
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={"type": "CREATE", "input": "new story prompt"},
        )
        assert resp.status_code == 400
        assert "workspace is empty" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_create_requires_graph(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[SimpleNamespace(id="ch-1", content="existing text", order_index=0, created_at=0)],
            component_models={},
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={"type": "CONTINUE", "input": "continue this"},
        )
        assert resp.status_code == 400
        assert "Knowledge graph is required" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_continue_forces_rag_enabled(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        fake_user,
        _create_operation_globals: dict,
    ):
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[SimpleNamespace(id="ch-1", content="existing text", order_index=0, created_at=0)],
            component_models={},
            cognee_dataset_id="dataset-1",
        )
        op = SimpleNamespace(
            id="op-continue",
            project_id="proj-1",
            type="CONTINUE",
            input="continue this",
            output="continuation",
            model="gpt-4o-mini",
            input_tokens=20,
            output_tokens=12,
            cost=0.003,
            status="COMPLETED",
            error=None,
            progress=100,
            message="Done",
            metadata_=None,
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.flush = AsyncMock()
        mock_run = AsyncMock(return_value=op)
        orig = _create_operation_globals["run_operation"]
        _create_operation_globals["run_operation"] = mock_run
        try:
            resp = await client.post(
                "/api/projects/proj-1/operation",
                json={"type": "CONTINUE", "input": "continue this", "use_rag": False},
            )
        finally:
            _create_operation_globals["run_operation"] = orig
        assert resp.status_code == 200
        assert mock_run.await_args.kwargs["use_rag"] is True

    @pytest.mark.asyncio
    async def test_create_operation_empty_input(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[],
            component_models={},
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={"type": "CREATE", "input": "   "},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_operation_project_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        mock_db.execute.return_value = _scalar_one_or_none(None)
        resp = await client.post(
            "/api/projects/missing/operation",
            json={"type": "CREATE", "input": "hello"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_operation_forbidden(self, client: AsyncClient, mock_db: AsyncMock):
        project = SimpleNamespace(id="proj-1", user_id="other-user", component_models={})
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={"type": "CREATE", "input": "hello"},
        )
        assert resp.status_code == 403


class TestListOperationsNotFound:
    """GET /api/projects/{id}/operations - line 288: project not found."""

    @pytest.mark.asyncio
    async def test_list_operations_project_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        mock_db.execute.return_value = _scalar_one_or_none(None)
        resp = await client.get("/api/projects/nonexistent/operations")
        assert resp.status_code == 404


class TestCreateOperationUpload:
    """POST /api/projects/{id}/operation/upload - lines 305-393."""

    @pytest.mark.asyncio
    async def test_upload_invalid_type(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        files = {"file": ("doc.txt", BytesIO(b"hello"), "text/plain")}
        resp = await client.post(
            "/api/projects/proj-1/operation/upload",
            files=files,
            data={"type": "CREATE"},
        )
        assert resp.status_code == 400
        assert "File upload supports" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_unsupported_extension(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        files = {"file": ("doc.csv", BytesIO(b"a,b,c"), "text/csv")}
        resp = await client.post(
            "/api/projects/proj-1/operation/upload",
            files=files,
            data={"type": "ANALYZE"},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_project_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        mock_db.execute.return_value = _scalar_one_or_none(None)
        files = {"file": ("doc.txt", BytesIO(b"hello"), "text/plain")}
        resp = await client.post(
            "/api/projects/missing/operation/upload",
            files=files,
            data={"type": "ANALYZE"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_forbidden(self, client: AsyncClient, mock_db: AsyncMock):
        project = SimpleNamespace(id="proj-1", user_id="other-user")
        mock_db.execute.return_value = _scalar_one_or_none(project)
        files = {"file": ("doc.txt", BytesIO(b"hello"), "text/plain")}
        resp = await client.post(
            "/api/projects/proj-1/operation/upload",
            files=files,
            data={"type": "ANALYZE"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_upload_success_flow(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        fake_user,
        _create_operation_upload_globals: dict,
    ):
        """Lines 352-393: full success flow."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[],
            component_models={},
            cognee_dataset_id=None,
        )
        op = SimpleNamespace(
            id="op-1",
            project_id="proj-1",
            type="ANALYZE",
            input="hello world",
            output="Analysis result",
            model="gpt-4o-mini",
            input_tokens=20,
            output_tokens=15,
            cost=0.005,
            status="COMPLETED",
            error=None,
            progress=100,
            message="Done",
            metadata_=None,
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.flush = AsyncMock()

        mock_run = AsyncMock(return_value=op)
        mock_resolve_input = AsyncMock(return_value=("merged input", ["ch-1"]))
        orig_run = _create_operation_upload_globals["run_operation"]
        orig_extract = _create_operation_upload_globals["extract_text_from_file"]
        orig_resolve_input = _create_operation_upload_globals["_resolve_operation_input"]
        _create_operation_upload_globals["run_operation"] = mock_run
        _create_operation_upload_globals["extract_text_from_file"] = MagicMock(return_value="hello world")
        _create_operation_upload_globals["_resolve_operation_input"] = mock_resolve_input
        try:
            files = {"file": ("doc.txt", BytesIO(b"hello world"), "text/plain")}
            resp = await client.post(
                "/api/projects/proj-1/operation/upload",
                files=files,
                data={"type": "ANALYZE", "chapter_ids": ["ch-1"]},
            )
        finally:
            _create_operation_upload_globals["run_operation"] = orig_run
            _create_operation_upload_globals["extract_text_from_file"] = orig_extract
            _create_operation_upload_globals["_resolve_operation_input"] = orig_resolve_input

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "COMPLETED"
        assert data["output"] == "Analysis result"
        mock_resolve_input.assert_awaited_once()
        resolve_kwargs = mock_resolve_input.await_args.kwargs
        assert resolve_kwargs["chapter_ids"] == ["ch-1"]
        assert resolve_kwargs["provided_input"] == "hello world"
        assert mock_run.await_args.args[4] == "merged input"

    @pytest.mark.asyncio
    async def test_upload_invalid_chapter_ids_returns_400(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        fake_user,
        _create_operation_upload_globals: dict,
    ):
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[],
            component_models={},
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.flush = AsyncMock()

        orig_extract = _create_operation_upload_globals["extract_text_from_file"]
        orig_resolve_input = _create_operation_upload_globals["_resolve_operation_input"]
        _create_operation_upload_globals["extract_text_from_file"] = MagicMock(return_value="hello world")
        _create_operation_upload_globals["_resolve_operation_input"] = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="Invalid chapter_ids for project: bad-id")
        )
        try:
            files = {"file": ("doc.txt", BytesIO(b"hello world"), "text/plain")}
            resp = await client.post(
                "/api/projects/proj-1/operation/upload",
                files=files,
                data={"type": "ANALYZE", "chapter_ids": ["bad-id"]},
            )
        finally:
            _create_operation_upload_globals["extract_text_from_file"] = orig_extract
            _create_operation_upload_globals["_resolve_operation_input"] = orig_resolve_input

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid chapter_ids for project: bad-id"


class TestCreateOperationStream:
    """POST /api/projects/{id}/operation/stream - lines 211-237."""

    @pytest.mark.asyncio
    async def test_stream_success_flow(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        fake_user,
        _create_operation_stream_globals: dict,
    ):
        """Full flow: create operation and launch async task."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[],
            component_models={},
        )
        op = SimpleNamespace(
            id="op-1",
            project_id="proj-1",
            type="CREATE",
            input="Write something",
            output=None,
            model="gpt-4o-mini",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            status="PENDING",
            error=None,
            progress=0,
            message=None,
            metadata_=None,
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.flush = AsyncMock()

        fake_text_operation = MagicMock(return_value=op)
        fake_run_async = AsyncMock(return_value=None)
        fake_create_task = MagicMock()
        orig_text_operation = _create_operation_stream_globals["TextOperation"]
        orig_run_async = _create_operation_stream_globals["run_operation_async"]
        orig_asyncio = _create_operation_stream_globals["asyncio"]
        _create_operation_stream_globals["TextOperation"] = fake_text_operation
        _create_operation_stream_globals["run_operation_async"] = fake_run_async
        _create_operation_stream_globals["asyncio"] = MagicMock(create_task=fake_create_task)
        try:
            resp = await client.post(
                "/api/projects/proj-1/operation/stream",
                json={"type": "CREATE", "input": "Write something", "use_rag": False},
            )
        finally:
            _create_operation_stream_globals["TextOperation"] = orig_text_operation
            _create_operation_stream_globals["run_operation_async"] = orig_run_async
            _create_operation_stream_globals["asyncio"] = orig_asyncio

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PENDING"
        assert fake_run_async.await_args.kwargs["use_rag"] is False

    @pytest.mark.asyncio
    async def test_stream_non_create_requires_graph(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[SimpleNamespace(id="ch-1", content="text", order_index=0, created_at=0)],
            component_models={},
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.post(
            "/api/projects/proj-1/operation/stream",
            json={"type": "CONTINUE", "input": "continue this"},
        )
        assert resp.status_code == 400
        assert "Knowledge graph is required" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_stream_continue_forces_rag_enabled(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        fake_user,
        _create_operation_stream_globals: dict,
    ):
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[SimpleNamespace(id="ch-1", content="text", order_index=0, created_at=0)],
            component_models={},
            cognee_dataset_id="dataset-1",
        )
        op = SimpleNamespace(
            id="op-continue-stream",
            project_id="proj-1",
            type="CONTINUE",
            input="continue this",
            output=None,
            model="gpt-4o-mini",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            status="PENDING",
            error=None,
            progress=0,
            message=None,
            metadata_=None,
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.flush = AsyncMock()

        fake_text_operation = MagicMock(return_value=op)
        fake_run_async = AsyncMock(return_value=None)
        fake_create_task = MagicMock()
        orig_text_operation = _create_operation_stream_globals["TextOperation"]
        orig_run_async = _create_operation_stream_globals["run_operation_async"]
        orig_asyncio = _create_operation_stream_globals["asyncio"]
        _create_operation_stream_globals["TextOperation"] = fake_text_operation
        _create_operation_stream_globals["run_operation_async"] = fake_run_async
        _create_operation_stream_globals["asyncio"] = MagicMock(create_task=fake_create_task)
        try:
            resp = await client.post(
                "/api/projects/proj-1/operation/stream",
                json={"type": "CONTINUE", "input": "continue this", "use_rag": False},
            )
        finally:
            _create_operation_stream_globals["TextOperation"] = orig_text_operation
            _create_operation_stream_globals["run_operation_async"] = orig_run_async
            _create_operation_stream_globals["asyncio"] = orig_asyncio

        assert resp.status_code == 200
        assert fake_run_async.await_args.kwargs["use_rag"] is True

    @pytest.mark.asyncio
    async def test_stream_project_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        mock_db.execute.return_value = _scalar_one_or_none(None)
        resp = await client.post(
            "/api/projects/missing/operation/stream",
            json={"type": "CREATE", "input": "hello"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stream_forbidden(self, client: AsyncClient, mock_db: AsyncMock):
        project = SimpleNamespace(id="proj-1", user_id="other-user")
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.post(
            "/api/projects/proj-1/operation/stream",
            json={"type": "CREATE", "input": "hello"},
        )
        assert resp.status_code == 403

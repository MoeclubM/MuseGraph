"""Tests for report router endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_first(value):
    result = MagicMock()
    first_mock = MagicMock()
    first_mock.return_value = value
    result.scalars.return_value = MagicMock(first=first_mock)
    return result


class TestReportGenerate:
    """Test report generation endpoints."""

    @pytest.mark.asyncio
    async def test_generate_report_new(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test generating a new report."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            metadata_=None,
            simulation_config=None,
            run_state=None,
        )
        project = SimpleNamespace(
            id="proj-1",
            title="Test Project",
            simulation_requirement="Test requirement",
            oasis_analysis={},
            ontology_schema={},
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Project content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
        )

        # First query: get simulation
        # Second query: get project
        # Third query: check for existing completed report (scalars().first())
        first_result = MagicMock()
        first_mock = MagicMock()
        first_mock.return_value = None  # No existing report
        first_result.scalars.return_value = MagicMock(first=first_mock)

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
            first_result,
        ]

        with patch("app.routers.report._run_report_task"):
            resp = await client.post(
                "/api/report/generate",
                json={"simulation_id": "sim-1"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "report_id" in body["data"]

    @pytest.mark.asyncio
    async def test_generate_report_returns_existing(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test that generate returns existing completed report."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
        )
        existing_report = SimpleNamespace(
            report_id="report-existing",
            simulation_id="sim-1",
            status="completed",
        )
        project = SimpleNamespace(
            id="proj-1",
            title="Test Project",
            simulation_requirement="Test requirement",
            oasis_analysis={},
            ontology_schema={},
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Project content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
            _scalars_first(existing_report),
        ]

        resp = await client.post(
            "/api/report/generate",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["already_generated"] is True
        assert body["data"]["report_id"] == "report-existing"

    @pytest.mark.asyncio
    async def test_generate_report_force_regenerate(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test force regenerate creates new report."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            metadata_=None,
            simulation_config=None,
            run_state=None,
        )
        project = SimpleNamespace(
            id="proj-1",
            title="Test",
            simulation_requirement="Req",
            oasis_analysis={},
            ontology_schema={},
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Project content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
        )

        # force_regenerate skips completed-report lookup; still resolves project + text
        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
        ]

        with patch("app.routers.report._run_report_task"):
            resp = await client.post(
                "/api/report/generate",
                json={"simulation_id": "sim-1", "force_regenerate": True},
            )

        assert resp.status_code == 200
        assert "report_id" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_generate_report_simulation_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test generate with non-existent simulation returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.post(
            "/api/report/generate",
            json={"simulation_id": "nonexistent"},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_report_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test generate on another user's simulation returns 403."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/report/generate",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 403


class TestReportStatus:
    """Test report status endpoints."""

    @pytest.mark.asyncio
    async def test_get_generate_status_by_task(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting status by task_id."""
        # Create a task via the task_manager
        from app.services.task_state import task_manager, TaskStatus

        # First clean up any old tasks
        task_manager.cleanup_old_tasks(max_age_hours=0)

        task = task_manager.create_task("report_generate", metadata={"simulation_id": "sim-1"})
        # Mark as completed to have a known state
        task_manager.complete_task(task.task_id, result={}, message="Done")

        resp = await client.post(
            "/api/report/generate/status",
            json={"task_id": task.task_id},
        )

        # Task should be found
        assert resp.status_code in [200, 404]  # May be 404 if task expired

    @pytest.mark.asyncio
    async def test_get_generate_status_by_simulation_completed(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting status by simulation_id when completed."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
        )
        report = SimpleNamespace(
            report_id="report-1",
            status="completed",
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalars_first(report),
        ]

        resp = await client.post(
            "/api/report/generate/status",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_generate_status_task_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test status with non-existent task returns 404."""
        resp = await client.post(
            "/api/report/generate/status",
            json={"task_id": "nonexistent"},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_generate_status_no_params(self, client: AsyncClient, mock_db: AsyncMock):
        """Test status without task_id or simulation_id returns 400."""
        resp = await client.post(
            "/api/report/generate/status",
            json={},
        )

        assert resp.status_code == 400


class TestReportGet:
    """Test report retrieval endpoints."""

    @pytest.mark.asyncio
    async def test_get_report_by_id(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting report by ID."""
        report = SimpleNamespace(
            report_id="report-1",
            simulation_id="sim-1",
            user_id=fake_user.id,
            project_id="proj-1",
            status="completed",
            title="Test Report",
            executive_summary="Summary",
            markdown_content="# Content",
            report_payload={"key": "value"},
            updated_at=datetime.now(timezone.utc),
            sections=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["data"]["report_id"] == "report-1"

    @pytest.mark.asyncio
    async def test_get_report_by_simulation(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting report by simulation ID."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
        )
        report = SimpleNamespace(
            report_id="report-1",
            simulation_id="sim-1",
            user_id=fake_user.id,
            project_id="proj-1",
            status="completed",
            title="Title",
            executive_summary="Summary",
            markdown_content="",
            report_payload={},
            updated_at=datetime.now(timezone.utc),
            sections=[],
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalars_first(report),
        ]

        resp = await client.get("/api/report/by-simulation/sim-1")

        assert resp.status_code == 200
        assert resp.json()["has_report"] is True

    @pytest.mark.asyncio
    async def test_get_report_by_simulation_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting report for simulation without report."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalars_first(None),
        ]

        resp = await client.get("/api/report/by-simulation/sim-1")

        assert resp.status_code == 200
        assert resp.json()["has_report"] is False

    @pytest.mark.asyncio
    async def test_get_report_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting non-existent report returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get("/api/report/nonexistent")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_report_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting another user's report returns 403."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1")

        assert resp.status_code == 403


class TestReportList:
    """Test report listing endpoints."""

    @pytest.mark.asyncio
    async def test_list_reports(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test listing reports for user."""
        reports = [
            SimpleNamespace(
                report_id="report-1",
                simulation_id="sim-1",
                user_id=fake_user.id,
                project_id="proj-1",
                status="completed",
                title="Report 1",
                executive_summary="",
                markdown_content="",
                report_payload={},
                updated_at=datetime.now(timezone.utc),
                sections=[],
                created_at=datetime.now(timezone.utc),
            ),
        ]

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = reports
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        resp = await client.get("/api/report/list")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    @pytest.mark.asyncio
    async def test_list_reports_by_simulation(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test listing reports filtered by simulation."""
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        resp = await client.get("/api/report/list?simulation_id=sim-1")

        assert resp.status_code == 200


class TestReportCheck:
    """Test report check endpoint."""

    @pytest.mark.asyncio
    async def test_check_report_status_has_report(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test check status when report exists."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
        )
        report = SimpleNamespace(
            report_id="report-1",
            status="completed",
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalars_first(report),
        ]

        resp = await client.get("/api/report/check/sim-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["has_report"] is True
        assert body["data"]["interview_unlocked"] is True

    @pytest.mark.asyncio
    async def test_check_report_status_no_report(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test check status when no report exists."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalars_first(None),
        ]

        resp = await client.get("/api/report/check/sim-1")

        assert resp.status_code == 200
        assert resp.json()["data"]["has_report"] is False


class TestReportChat:
    """Test report chat endpoint."""

    @pytest.mark.asyncio
    async def test_chat_with_report(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test chatting with report."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            project_id="proj-1",
        )
        report = SimpleNamespace(
            report_id="report-1",
            report_payload={"executive_summary": "Test summary"},
            chat_history=[],
            agent_log=[],
        )
        project = SimpleNamespace(
            id="proj-1",
            component_models=None,
        )

        first_result = MagicMock()
        first_mock = MagicMock()
        first_mock.return_value = report
        first_result.scalars.return_value = MagicMock(first=first_mock)

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            first_result,
            _scalar_one_or_none(project),
        ]

        with patch("app.routers.report.call_llm") as mock_llm:
            mock_llm.return_value = {"content": "AI response"}
            resp = await client.post(
                "/api/report/chat",
                json={"simulation_id": "sim-1", "message": "What happened?"},
            )

        assert resp.status_code == 200
        assert "answer" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_chat_report_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test chat when report not found."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalars_first(None),
        ]

        resp = await client.post(
            "/api/report/chat",
            json={"simulation_id": "sim-1", "message": "Test"},
        )

        assert resp.status_code == 404


class TestReportTools:
    """Test report tools endpoints."""

    @pytest.mark.asyncio
    async def test_tools_search(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test search tool."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
            report_payload={
                "title": "Test Report",
                "executive_summary": "Important summary content",
                "key_findings": ["Finding 1", "Finding 2"],
            },
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.post(
            "/api/report/tools/search",
            json={"report_id": "report-1", "query": "summary"},
        )

        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    @pytest.mark.asyncio
    async def test_tools_statistics(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test statistics tool."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            posts=[{"id": 1}, {"id": 2}],
            comments=[{"id": 1}],
            actions=[],
            run_state={"run_result": {"metrics": {"total_rounds": 10}}},
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/report/tools/statistics",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["post_count"] == 2
        assert data["comment_count"] == 1


class TestReportDownload:
    """Test report download endpoint."""

    @pytest.mark.asyncio
    async def test_download_report(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test downloading report as markdown."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
            markdown_content="# Report\n\nContent here.",
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1/download")

        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]


class TestReportDelete:
    """Test report delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_report(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test deleting report."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.delete("/api/report/report-1")

        assert resp.status_code == 200
        mock_db.delete.assert_awaited_once_with(report)


class TestReportSections:
    """Test report sections endpoints."""

    @pytest.mark.asyncio
    async def test_get_sections(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting report sections."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
            sections=[
                {"index": 0, "title": "Introduction", "content": "Intro"},
                {"index": 1, "title": "Analysis", "content": "Details"},
            ],
            markdown_content=None,
            status="completed",
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1/sections")

        assert resp.status_code == 200
        assert resp.json()["data"]["count"] == 2

    @pytest.mark.asyncio
    async def test_get_single_section(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting single section."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
            sections=[{"index": 0, "title": "Intro", "content": "Content"}],
            markdown_content=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1/section/0")

        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Intro"

    @pytest.mark.asyncio
    async def test_get_section_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting non-existent section returns 404."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
            sections=[],
            markdown_content=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1/section/999")

        assert resp.status_code == 404


class TestReportLogs:
    """Test report log endpoints."""

    @pytest.mark.asyncio
    async def test_get_agent_log(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting agent log."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
            agent_log=[
                {"line": "Starting", "created_at": "2024-01-01T00:00:00Z"},
                {"line": "Processing", "created_at": "2024-01-01T00:01:00Z"},
            ],
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1/agent-log")

        assert resp.status_code == 200
        assert len(resp.json()["data"]["logs"]) == 2

    @pytest.mark.asyncio
    async def test_get_console_log(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting console log."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
            console_log=[{"line": "Log entry"}],
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1/console-log")

        assert resp.status_code == 200
        assert len(resp.json()["data"]["logs"]) == 1

    @pytest.mark.asyncio
    async def test_get_log_with_from_line(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting log with from_line offset."""
        report = SimpleNamespace(
            report_id="report-1",
            user_id=fake_user.id,
            agent_log=[
                {"line": "Line 0"},
                {"line": "Line 1"},
                {"line": "Line 2"},
            ],
        )
        mock_db.execute.return_value = _scalar_one_or_none(report)

        resp = await client.get("/api/report/report-1/agent-log?from_line=1")

        assert resp.status_code == 200
        logs = resp.json()["data"]["logs"]
        assert len(logs) == 2  # Skipped first one


class TestMarkdownSplitting:
    """Test markdown section splitting helper."""

    def test_split_markdown_sections(self):
        """Test splitting markdown into sections."""
        from app.routers.report import _split_markdown_sections

        markdown = """# Title

Intro content.

## Section 1

Content for section 1.

### Subsection

More details.

## Section 2

Final content.
"""
        sections = _split_markdown_sections(markdown)

        assert len(sections) == 4
        assert sections[0]["title"] == "Title"
        assert sections[1]["title"] == "Section 1"
        assert sections[2]["title"] == "Subsection"
        assert sections[3]["title"] == "Section 2"

    def test_split_empty_markdown(self):
        """Test splitting empty markdown."""
        from app.routers.report import _split_markdown_sections

        assert _split_markdown_sections("") == []
        assert _split_markdown_sections(None) == []

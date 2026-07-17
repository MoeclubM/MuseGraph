"""Tests for export service functions."""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest

from app.services.export import export_project_bundle_sync


def _mk_project(
    *,
    title: str | None = "Test Project",
    description: str | None = "Test description",
    chapter_contents: list[str | None] | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    project_id: str = "proj-export-1",
):
    chapters = []
    for idx, text in enumerate(chapter_contents or []):
        chapters.append(
            SimpleNamespace(
                id=f"ch-{idx + 1}",
                title=f"Chapter {idx + 1}",
                status="draft",
                blueprint=None,
                plan=None,
                summary=None,
                continuity_notes=None,
                order_index=idx,
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                content=text,
            )
        )
    return SimpleNamespace(
        id=project_id,
        title=title,
        description=description,
        visibility="private",
        component_models=None,
        operation_prompts=None,
        ontology_schema=None,
        creative_state=None,
        memory_id=None,
        chapters=chapters,
        created_at=created_at or datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=updated_at or datetime(2024, 1, 2, tzinfo=timezone.utc),
    )


class TestExportProjectBundle:
    """Test export_project_bundle_sync."""

    def test_bundle_contains_manifest_and_chapter(self, tmp_path, monkeypatch):
        """ZIP includes project manifest and chapter markdown."""
        from app.services import project_files

        workspace = tmp_path / "projects" / "proj-export-1" / "workspace"
        workspace.mkdir(parents=True)
        monkeypatch.setattr(project_files, "_storage_root", lambda: tmp_path)

        project = _mk_project(chapter_contents=["Hello bundle."])
        content, content_type, filename = export_project_bundle_sync(
            project,
            list(project.chapters),
            [],
        )

        assert content_type == "application/zip"
        assert filename == "Test Project.zip"
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            assert ".musegraph/project.json" in names
            assert "documents/ch-1.md" in names
            doc = archive.read("documents/ch-1.md").decode("utf-8")
            assert "Hello bundle." in doc

    def test_bundle_sanitizes_filename(self, tmp_path, monkeypatch):
        from app.services import project_files

        workspace = tmp_path / "projects" / "p2" / "workspace"
        workspace.mkdir(parents=True)
        monkeypatch.setattr(project_files, "_storage_root", lambda: tmp_path)

        project = _mk_project(
            title='Bad<>:"|?*',
            project_id="p2",
            chapter_contents=["x"],
        )
        _, _, filename = export_project_bundle_sync(project, list(project.chapters), [])
        assert filename.endswith(".zip")
        assert "<" not in filename

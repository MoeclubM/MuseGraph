"""Tests for export service functions."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.export import export_project


def _mk_project(
    *,
    title: str | None = "Test Project",
    description: str | None = "Test description",
    chapter_contents: list[str | None] | None = None,
    content: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
):
    chapters = []
    for idx, text in enumerate(chapter_contents or []):
        chapters.append(
            SimpleNamespace(
                id=f"ch-{idx + 1}",
                order_index=idx,
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                content=text,
            )
        )
    payload = {
        "title": title,
        "description": description,
        "chapters": chapters,
        "created_at": created_at or datetime(2024, 1, 1, tzinfo=timezone.utc),
        "updated_at": updated_at or datetime(2024, 1, 2, tzinfo=timezone.utc),
    }
    if content is not None:
        payload["content"] = content
    return SimpleNamespace(**payload)


class TestExportProject:
    """Test export_project function for all formats."""

    @pytest.mark.asyncio
    async def test_export_txt_format(self):
        """Test exporting project as plain text."""
        project = _mk_project(chapter_contents=["This is the content."])
        content, content_type, filename = await export_project(project, "txt")

        assert content == b"This is the content."
        assert content_type == "text/plain; charset=utf-8"
        assert filename == "Test Project.txt"

    @pytest.mark.asyncio
    async def test_export_txt_with_none_content(self):
        """Test exporting project with None chapter content as txt."""
        project = _mk_project(title="Empty Project", description="Desc", chapter_contents=[None])
        content, content_type, filename = await export_project(project, "txt")

        assert content == b""
        assert filename == "Empty Project.txt"

    @pytest.mark.asyncio
    async def test_export_json_format(self):
        """Test exporting project as JSON."""
        created = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        updated = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        project = _mk_project(
            title="JSON Project",
            description="JSON description",
            chapter_contents=["JSON content"],
            created_at=created,
            updated_at=updated,
        )
        content, content_type, filename = await export_project(project, "json")

        import json
        data = json.loads(content)

        assert data["title"] == "JSON Project"
        assert data["description"] == "JSON description"
        assert data["content"] == "JSON content"
        assert "2024-01-01" in data["created_at"]
        assert content_type == "application/json; charset=utf-8"
        assert filename == "JSON Project.json"

    @pytest.mark.asyncio
    async def test_export_md_format(self):
        """Test exporting project as Markdown."""
        project = _mk_project(
            title="MD Project",
            description="MD description",
            chapter_contents=["Markdown content here."],
        )
        content, content_type, filename = await export_project(project, "md")
        content_str = content.decode("utf-8")

        assert "# MD Project" in content_str
        assert "MD description" in content_str
        assert "Markdown content here." in content_str
        assert "---" in content_str
        assert content_type == "text/markdown; charset=utf-8"
        assert filename == "MD Project.md"

    @pytest.mark.asyncio
    async def test_export_md_without_description(self):
        """Test exporting project as Markdown without description."""
        project = _mk_project(
            title="No Desc",
            description=None,
            chapter_contents=["Content only."],
        )
        content, _, _ = await export_project(project, "md")
        content_str = content.decode("utf-8")

        assert "# No Desc" in content_str
        assert "Content only." in content_str

    @pytest.mark.asyncio
    async def test_export_html_format(self):
        """Test exporting project as HTML."""
        project = _mk_project(
            title="HTML Project",
            description="HTML description",
            chapter_contents=["Line 1\nLine 2\nLine 3"],
        )
        content, content_type, filename = await export_project(project, "html")
        content_str = content.decode("utf-8")

        assert "<!DOCTYPE html>" in content_str
        assert "<title>HTML Project</title>" in content_str
        assert "<h1>HTML Project</h1>" in content_str
        assert "<em>HTML description</em>" in content_str
        assert "<br>" in content_str  # newlines converted to <br>
        assert content_type == "text/html; charset=utf-8"
        assert filename == "HTML Project.html"

    @pytest.mark.asyncio
    async def test_export_html_without_description(self):
        """Test exporting project as HTML without description."""
        project = _mk_project(
            title="No Desc HTML",
            description=None,
            chapter_contents=["HTML content"],
        )
        content, _, _ = await export_project(project, "html")
        content_str = content.decode("utf-8")

        assert "<em>" not in content_str

    @pytest.mark.asyncio
    async def test_export_sanitizes_filename(self):
        """Test that special characters are removed from filename."""
        project = _mk_project(
            title='Test/Project<>:"|?*Name',
            description=None,
            chapter_contents=["Content"],
        )
        _, _, filename = await export_project(project, "txt")

        assert "/" not in filename
        assert "<" not in filename
        assert ">" not in filename
        assert ":" not in filename
        assert '"' not in filename
        assert "|" not in filename
        assert "?" not in filename
        assert "*" not in filename

    @pytest.mark.asyncio
    async def test_export_truncates_long_title(self):
        """Test that long titles are truncated in filename."""
        long_title = "A" * 100
        project = _mk_project(
            title=long_title,
            description=None,
            chapter_contents=["Content"],
        )
        _, _, filename = await export_project(project, "txt")

        assert len(filename) <= 54  # 50 + ".txt"

    @pytest.mark.asyncio
    async def test_export_unsupported_format(self):
        """Test exporting with unsupported format raises error."""
        project = _mk_project(
            title="Test",
            description=None,
            chapter_contents=["Content"],
        )

        with pytest.raises(ValueError, match="Unsupported format"):
            await export_project(project, "pdf")

    @pytest.mark.asyncio
    async def test_export_untitled_project(self):
        """Test exporting project with no title uses 'untitled'."""
        project = _mk_project(
            title=None,
            description=None,
            chapter_contents=["Content"],
        )
        _, _, filename = await export_project(project, "txt")

        assert filename.startswith("untitled")

    @pytest.mark.asyncio
    async def test_export_preserves_unicode(self):
        """Test that unicode characters are preserved."""
        project = _mk_project(
            title="Test",
            description="Description",
            chapter_contents=["Unicode content emojis"],
        )
        content, _, _ = await export_project(project, "txt")

        assert b"Unicode" in content

    @pytest.mark.asyncio
    async def test_export_json_with_none_values(self):
        """Test JSON export handles empty chapter content as empty string."""
        project = _mk_project(
            title="Project",
            description=None,
            chapter_contents=[None],
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        content, _, _ = await export_project(project, "json")

        import json
        data = json.loads(content)

        assert data["title"] == "Project"
        assert data["description"] is None
        assert data["content"] == ""

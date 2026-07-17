from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.chapter_writeback import write_chapter_content
from app.services.creative_workflow import chapter_memory_text, render_workflow_memory


def test_chapter_memory_text_renders_as_document_unit_memory():
    unit = SimpleNamespace(
        id="unit-1",
        title="",
        order_index=0,
        status="draft",
        blueprint={"goal": "Explain product architecture"},
        plan="Write the architecture section.",
        summary="Architecture summary.",
        continuity_notes={"terms": ["Cognee"]},
        content="MuseGraph uses agent-driven retrieval.",
    )

    text = chapter_memory_text(unit)

    assert "[Document Unit Memory]" in text
    assert "[Unit Blueprint]" in text
    assert "[Unit Text]" in text
    assert "Document Unit 1" in text
    assert "[Chapter Memory]" not in text
    assert "[Chapter Text]" not in text


def test_render_workflow_memory_uses_generic_document_unit_contract():
    block = render_workflow_memory({
        "workflow_step": "agent_generate",
        "chapter_count": 2,
        "written_chapter_count": 1,
        "target_chapters": [{"id": "u2", "order_index": 1, "title": "Section", "status": "planned"}],
        "previous_target_chapter": {"order_index": 0, "title": "Intro", "status": "draft", "content_tail": "尾段"},
        "chapters": [{"order_index": 0, "title": "Intro", "status": "draft"}],
        "execution_contract": [
            "Use Cognee relationships and source evidence to decide which facts are authoritative before changing established project state.",
        ],
    })

    assert "document units written" in block
    assert "Target document unit(s)" in block
    assert "Previous unit" in block
    assert "Document unit plan / summary ledger" in block
    assert "chapter(s)" not in block
    assert "canon" not in block.lower()


@pytest.mark.asyncio
async def test_write_chapter_content_default_title_is_document_unit():
    project = SimpleNamespace(id="proj-1", chapters=[])
    db = SimpleNamespace(add=lambda _obj: None, flush=AsyncMock())

    result = await write_chapter_content(
        project=project,
        db=db,
        content="这是一段足够长的通用文档正文，用于验证 Agent 写回新建文档单元时不会再使用章节默认标题。" * 2,
        mode="replace",
    )

    assert result["ok"] is True
    assert result["title"] == "Document Unit 1"
    assert project.chapters[0].title == "Document Unit 1"

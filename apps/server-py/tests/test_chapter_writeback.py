from app.services.chapter_writeback import (
    collect_prose_candidates,
    extract_text_content,
    pick_best_prose_candidate,
    pick_prose_from_agent_steps,
    resolve_write_mode,
)
from app.models.project import ProjectChapter


def test_extract_text_content_finds_nested_story():
    payload = {
        "structured_memory": {
            "worldview": "future mars",
            "draft": "A" * 250,
        }
    }
    assert len(extract_text_content(payload)) >= 200


def test_collect_prose_candidates_prefers_longest():
    candidates = collect_prose_candidates(
        {"output": "short"},
        {"content": "B" * 300},
        "C" * 120,
    )
    assert candidates[0] == "B" * 300
    assert pick_best_prose_candidate(candidates) == "B" * 300


def test_pick_prose_from_agent_steps_prefers_latest_write_step():
    prose = pick_prose_from_agent_steps([
        {"step_type": "analyze", "status": "completed", "output": '{"worldview":"mars"}'},
        {"step_type": "generate_document_unit", "status": "completed", "output": "D" * 220},
    ])
    assert prose == "D" * 220


def test_resolve_write_mode_creates_new_chapter_when_all_filled():
    chapters = [
        ProjectChapter(project_id="p1", title="第一章", content="已有正文", order_index=0),
    ]
    assert resolve_write_mode(mode="append", chapters=chapters, is_continuation=True) == "create"
"""Helpers for persisting agent-generated prose into project document units."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import ProjectChapter, TextProject

_PROSE_KEYS = (
    "content",
    "output",
    "text",
    "document_unit_text",
    "unit_text",
    "section_text",
    "正文",
    "draft",
    "story",
    "prose",
    "body",
    "document_content",
    "unit_content",
    "section_content",
    "full_text",
    "generated_content",
    "generated_text",
)

_MIN_PROSE_CHARS = 80
_WRITE_STEP_TYPES = frozenset({
    "write_chapter",
    "write_document_unit",
    "write_document_unit",
})


def extract_text_content(value: Any, *, _depth: int = 0) -> str:
    if value is None or _depth > 8:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
                nested = extract_text_content(parsed, _depth=_depth + 1)
                if len(nested) >= _MIN_PROSE_CHARS:
                    return nested
            except json.JSONDecodeError:
                pass
        return text
    if isinstance(value, dict):
        for key in _PROSE_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and len(candidate.strip()) >= _MIN_PROSE_CHARS:
                return candidate.strip()
            nested = extract_text_content(candidate, _depth=_depth + 1)
            if len(nested) >= _MIN_PROSE_CHARS:
                return nested
        nested_candidates = [
            extract_text_content(item, _depth=_depth + 1)
            for item in value.values()
        ]
        nested_candidates = [c for c in nested_candidates if len(c) >= _MIN_PROSE_CHARS]
        if nested_candidates:
            return max(nested_candidates, key=len)
    if isinstance(value, list):
        nested_candidates = [
            extract_text_content(item, _depth=_depth + 1)
            for item in value
        ]
        nested_candidates = [c for c in nested_candidates if len(c) >= _MIN_PROSE_CHARS]
        if nested_candidates:
            return max(nested_candidates, key=len)
    return str(value).strip()


def collect_prose_candidates(*sources: Any) -> list[str]:
    """Gather unique prose candidates from nested agent payloads."""
    seen: set[str] = set()
    results: list[str] = []

    def _add(candidate: str) -> None:
        text = candidate.strip()
        if len(text) < _MIN_PROSE_CHARS or text in seen:
            return
        seen.add(text)
        results.append(text)

    for source in sources:
        if source is None:
            continue
        if isinstance(source, str):
            _add(extract_text_content(source))
            continue
        if isinstance(source, dict):
            _add(extract_text_content(source))
            for key, value in source.items():
                if isinstance(value, str) and len(value.strip()) >= _MIN_PROSE_CHARS:
                    _add(value.strip())
                else:
                    _add(extract_text_content(value))
            continue
        if isinstance(source, list):
            for item in source:
                _add(extract_text_content(item))

    return sorted(results, key=len, reverse=True)


def pick_best_prose_candidate(candidates: list[str], *, min_chars: int = 200) -> str:
    if not candidates:
        return ""
    for candidate in candidates:
        if len(candidate) >= min_chars:
            return candidate
    return candidates[0] if len(candidates[0]) >= _MIN_PROSE_CHARS else ""


def _looks_like_structured_dump(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith("{") and not stripped.startswith("["):
        return False
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    if isinstance(parsed, dict):
        keys = {str(key).lower() for key in parsed.keys()}
        structured_keys = {
            "worldview", "characters", "plot", "timeline", "locations",
            "structured_memory", "memory_schema", "graph", "nodes", "edges",
        }
        return bool(keys & structured_keys)
    return isinstance(parsed, list)


def pick_prose_from_agent_steps(step_results: list[dict[str, Any]] | None) -> str:
    steps = step_results if isinstance(step_results, list) else []
    for step in reversed(steps):
        if str(step.get("status") or "").lower() not in {"completed", "success", "done"}:
            continue
        step_type = str(step.get("step_type") or step.get("tool") or "").strip().lower()
        if step_type not in _WRITE_STEP_TYPES and "write" not in step_type and "generate" not in step_type:
            continue
        prose = extract_text_content(step.get("output") or step.get("result") or step.get("content"))
        if len(prose) >= _MIN_PROSE_CHARS and not _looks_like_structured_dump(prose):
            return prose
    return ""


def pick_prose_from_messages(messages: list[dict[str, Any]] | None) -> str:
    msgs = messages if isinstance(messages, list) else []
    for msg in reversed(msgs):
        if str(msg.get("role") or "") not in {"assistant", "agent"}:
            continue
        prose = extract_text_content(msg.get("content"))
        if len(prose) >= _MIN_PROSE_CHARS and not _looks_like_structured_dump(prose):
            return prose
    return ""


def resolve_write_mode(
    *,
    mode: str,
    chapters: list[ProjectChapter],
    is_continuation: bool,
) -> str:
    normalized_mode = str(mode or "append").strip().lower()
    if normalized_mode == "create":
        return "create"
    if not is_continuation:
        return normalized_mode
    if not chapters:
        return "create"
    has_empty = any(not (chapter.content or "").strip() for chapter in chapters)
    if has_empty:
        return "append"
    return "create"


async def write_chapter_content(
    *,
    project: TextProject,
    db: AsyncSession,
    content: str,
    chapter_id: str = "",
    title: str = "",
    mode: str = "append",
) -> dict[str, Any]:
    """Create or update a project document unit with agent-generated text."""
    text = extract_text_content(content)
    if not text:
        return {"ok": False, "error": "content is empty"}

    chapters = sorted(project.chapters or [], key=lambda c: c.order_index)
    normalized_mode = str(mode or "append").strip().lower()
    if normalized_mode == "append" and chapters and all((chapter.content or "").strip() for chapter in chapters):
        normalized_mode = "create"
    target: ProjectChapter | None = None
    if chapter_id:
        target = next((c for c in chapters if c.id == chapter_id), None)

    if normalized_mode != "create" and target is None and chapters:
        empty = next((c for c in chapters if not (c.content or "").strip()), None)
        target = empty or chapters[-1]

    if target is None:
        next_index = len(chapters)
        target = ProjectChapter(
            project_id=project.id,
            title=(title or f"Document Unit {next_index + 1}").strip() or f"Document Unit {next_index + 1}",
            content="",
            status="draft",
            order_index=next_index,
        )
        db.add(target)
        project.chapters = [*chapters, target]

    if normalized_mode in {"replace", "create"}:
        target.content = text
    else:
        existing = (target.content or "").strip()
        target.content = f"{existing}\n\n{text}".strip() if existing else text

    await db.flush()
    return {
        "ok": True,
        "chapter_id": target.id,
        "title": target.title,
        "mode": normalized_mode,
        "content_length": len(target.content or ""),
    }


async def ensure_chapter_from_agent_payload(
    *,
    project_id: str,
    plan_result: dict[str, Any] | None,
    step_results: list[dict[str, Any]] | None,
    messages: list[dict[str, Any]] | None,
    agent_workspace: dict[str, Any] | None,
    db: AsyncSession | None = None,
) -> dict[str, Any] | None:
    """Persist agent output when generated text only landed in messages/workspace."""
    from app.database import async_session

    owns_session = db is None
    session = db or async_session()
    try:
        result = await session.execute(
            select(TextProject)
            .where(TextProject.id == project_id)
            .options(selectinload(TextProject.chapters))
        )
        project = result.scalar_one_or_none()
        if project is None:
            return None

        plan = plan_result if isinstance(plan_result, dict) else {}
        workspace = agent_workspace if isinstance(agent_workspace, dict) else {}
        task_kind = str(plan.get("task_kind") or workspace.get("task_kind") or "")
        is_continuation = task_kind in {
            "chapter_continuation",
            "content_generation",
        } or "续写" in task_kind

        existing_chars = sum(len(ch.content or "") for ch in project.chapters or [])
        if existing_chars >= 200 and not is_continuation:
            return {"ok": True, "skipped": True, "reason": "document_unit_already_has_content"}
        steps = step_results if isinstance(step_results, list) else []
        msgs = messages if isinstance(messages, list) else []

        content = pick_prose_from_agent_steps(steps)
        if not content:
            content = pick_prose_from_messages(msgs)
        if not content:
            candidates = collect_prose_candidates(
                plan.get("output"),
                plan.get("content"),
                [
                    msg.get("content")
                    for msg in msgs
                    if str(msg.get("role") or "") in {"assistant", "agent"}
                ],
                [step.get("output") for step in reversed(steps) if step.get("status") == "completed"],
            )
            content = pick_best_prose_candidate(candidates)
        if not content:
            return {"ok": False, "error": "no prose candidate found"}

        title_hint = str(
            plan.get("task_kind") or plan.get("text_type") or workspace.get("task_kind") or "Agent Draft"
        )
        if is_continuation:
            title_hint = f"续写章节 {len(project.chapters or []) + 1}"
        write_mode = resolve_write_mode(
            mode="append" if is_continuation or existing_chars > 0 else "replace",
            chapters=list(project.chapters or []),
            is_continuation=is_continuation,
        )
        wb = await write_chapter_content(
            project=project,
            db=session,
            content=content,
            title=title_hint[:80],
            mode=write_mode,
        )
        if owns_session:
            await session.commit()
        else:
            await session.flush()
        return wb
    finally:
        if owns_session:
            await session.close()

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models.project import TextProject


def _text(value: Any) -> str:
    return str(value or "").strip()


def _chapter_order(chapter: Any) -> int:
    try:
        return int(getattr(chapter, "order_index", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _chapter_continuity_notes_text(chapter: Any) -> str:
    notes = getattr(chapter, "continuity_notes", None)
    if not notes:
        return ""
    if isinstance(notes, str):
        return notes.strip()
    return json.dumps(notes, ensure_ascii=False, sort_keys=True, default=str)


def _json_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def sorted_project_chapters(project: TextProject | Any) -> list[Any]:
    chapters = list(getattr(project, "chapters", None) or [])
    return sorted(chapters, key=lambda c: (_chapter_order(c), str(getattr(c, "created_at", "") or ""), _text(getattr(c, "id", ""))))


def chapter_has_memory_material(chapter: Any) -> bool:
    return any(
        _text(getattr(chapter, field, ""))
        for field in ("plan", "summary", "content")
    ) or bool(_json_text(getattr(chapter, "blueprint", None))) or bool(_chapter_continuity_notes_text(chapter))


def chapter_memory_text(chapter: Any) -> str:
    title = _text(getattr(chapter, "title", "")) or f"Document Unit {_chapter_order(chapter) + 1}"
    lines = [
        "[Document Unit Memory]",
        f"ID: {_text(getattr(chapter, 'id', ''))}",
        f"Order: {_chapter_order(chapter)}",
        f"Title: {title}",
        f"Status: {_text(getattr(chapter, 'status', 'draft')) or 'draft'}",
    ]
    blueprint = _json_text(getattr(chapter, "blueprint", None))
    if blueprint:
        lines.extend(["", "[Unit Blueprint]", blueprint])
    plan = _text(getattr(chapter, "plan", ""))
    if plan:
        lines.extend(["", "[Unit Plan]", plan])
    summary = _text(getattr(chapter, "summary", ""))
    if summary:
        lines.extend(["", "[Unit Summary]", summary])
    notes = _chapter_continuity_notes_text(chapter)
    if notes:
        lines.extend(["", "[Continuity Notes]", notes])
    content = _text(getattr(chapter, "content", ""))
    if content:
        lines.extend(["", "[Unit Text]", content])
    return "\n".join(lines).strip()


def chapter_memory_hash(chapter: Any) -> str:
    return hashlib.sha256(chapter_memory_text(chapter).encode("utf-8")).hexdigest()


def project_creative_state_text(project: TextProject | Any) -> str:
    state = getattr(project, "creative_state", None)
    if not isinstance(state, dict) or not state:
        return ""
    memory_state = dict(state)
    memory_state.pop("memory_build_state", None)
    if not memory_state:
        return ""
    return "[Creative State]\n" + json.dumps(memory_state, ensure_ascii=False, sort_keys=True, default=str)


def project_creative_state_hash(project: TextProject | Any) -> str:
    return hashlib.sha256(project_creative_state_text(project).encode("utf-8")).hexdigest()


def build_workflow_memory(
    project: TextProject | Any,
    *,
    workflow_step: str | None = None,
    target_chapter_ids: list[str] | None = None,
) -> dict[str, Any]:
    chapters = sorted_project_chapters(project)
    rows: list[dict[str, Any]] = []
    latest_content_row: dict[str, Any] | None = None
    next_planned_row: dict[str, Any] | None = None
    for chapter in chapters:
        content = _text(getattr(chapter, "content", ""))
        row = {
            "id": _text(getattr(chapter, "id", "")),
            "order_index": _chapter_order(chapter),
            "title": _text(getattr(chapter, "title", "")) or f"Document Unit {_chapter_order(chapter) + 1}",
            "status": _text(getattr(chapter, "status", "draft")) or "draft",
            "blueprint": _json_text(getattr(chapter, "blueprint", None)),
            "plan": _text(getattr(chapter, "plan", "")),
            "summary": _text(getattr(chapter, "summary", "")),
            "continuity_notes": _chapter_continuity_notes_text(chapter),
            "has_content": bool(content),
            "content_tail": content[-1200:].lstrip() if content else "",
        }
        rows.append(row)
        if row["has_content"]:
            latest_content_row = row
        elif row["plan"] and next_planned_row is None:
            next_planned_row = row
    target_ids = {_text(chapter_id) for chapter_id in target_chapter_ids or [] if _text(chapter_id)}
    target_rows = [row for row in rows if row["id"] in target_ids]
    previous_target_row: dict[str, Any] | None = None
    next_target_row: dict[str, Any] | None = None
    if target_rows:
        first_index = rows.index(target_rows[0])
        last_index = rows.index(target_rows[-1])
        if first_index > 0:
            previous_target_row = rows[first_index - 1]
        if last_index + 1 < len(rows):
            next_target_row = rows[last_index + 1]
    written_rows = [row for row in rows if row["has_content"] or row["summary"]]
    recent_summaries = [
        {
            "order_index": row["order_index"],
            "title": row["title"],
            "summary": row["summary"],
            "continuity_notes": row["continuity_notes"],
        }
        for row in written_rows[-6:]
        if row["summary"] or row["continuity_notes"]
    ]
    planned_rows = [
        {
            "order_index": row["order_index"],
            "title": row["title"],
            "plan": row["plan"],
            "blueprint": row["blueprint"],
        }
        for row in rows
        if row["plan"] and not row["has_content"]
    ][:12]

    return {
        "workflow_step": _text(workflow_step),
        "chapter_count": len(rows),
        "written_chapter_count": len([row for row in rows if row["has_content"]]),
        "latest_content_chapter": latest_content_row,
        "next_planned_chapter": next_planned_row,
        "target_chapters": target_rows,
        "previous_target_chapter": previous_target_row,
        "next_target_chapter": next_target_row,
        "recent_summaries": recent_summaries,
        "planned_chapters": planned_rows,
        "chapters": rows,
        "execution_contract": [
            "Treat unit plans, summaries, and continuity notes as explicit writing state.",
            "Use the latest unit ending or final paragraph as a causal handoff, not as text to repeat.",
            "Preserve established fact order, entity knowledge boundaries, relationship direction, and unresolved questions.",
            "Use cognee relationships and source evidence to decide which facts are authoritative before changing established project state.",
            "Draft material is not authoritative until the unit text and finalized state are saved.",
            "For planning steps, output a plan and consistency risks; for drafting steps, realize the approved plan without contradicting memory.",
        ],
    }


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)].rstrip() + "..."


def render_workflow_memory(workflow: dict[str, Any]) -> str:
    if not workflow:
        return ""

    lines: list[str] = [
        "Creative workflow state:",
        f"- Workflow step: {_truncate(workflow.get('workflow_step') or 'unspecified', 120)}",
        f"- Progress: {workflow.get('written_chapter_count', 0)}/{workflow.get('chapter_count', 0)} document units written",
    ]

    target_chapters = [row for row in workflow.get("target_chapters") or [] if isinstance(row, dict)]
    if target_chapters:
        target_lines: list[str] = []
        for row in target_chapters:
            detail = " | ".join(
                item
                for item in [
                    f"status={row.get('status')}",
                    f"blueprint={_truncate(row.get('blueprint'), 360)}" if row.get("blueprint") else "",
                    f"plan={_truncate(row.get('plan'), 320)}" if row.get("plan") else "",
                    f"summary={_truncate(row.get('summary'), 260)}" if row.get("summary") else "",
                    f"notes={_truncate(row.get('continuity_notes'), 260)}" if row.get("continuity_notes") else "",
                    f"current_tail={_truncate(row.get('content_tail'), 360)}" if row.get("content_tail") else "",
                ]
                if item
            )
            target_lines.append(f"- #{int(row.get('order_index') or 0) + 1} {row.get('title')}: {detail}")
        lines.append("Target document unit(s) for this operation:\n" + "\n".join(target_lines))

    previous_target = workflow.get("previous_target_chapter")
    if isinstance(previous_target, dict):
        lines.append(
            "- Previous unit: "
            + _truncate(
                f"#{int(previous_target.get('order_index') or 0) + 1} {previous_target.get('title')} [{previous_target.get('status')}]",
                220,
            )
        )
        previous_detail = " | ".join(
            item
            for item in [
                f"summary={_truncate(previous_target.get('summary'), 300)}" if previous_target.get("summary") else "",
                f"notes={_truncate(previous_target.get('continuity_notes'), 260)}" if previous_target.get("continuity_notes") else "",
            ]
            if item
        )
        if previous_detail:
            lines.append("Previous unit state:\n" + previous_detail)
        if previous_target.get("content_tail"):
            lines.append("Previous unit ending:\n" + _truncate(previous_target.get("content_tail"), 1200))

    next_target = workflow.get("next_target_chapter")
    if isinstance(next_target, dict):
        detail = " | ".join(
            item
            for item in [
                f"plan={_truncate(next_target.get('plan'), 320)}" if next_target.get("plan") else "",
                f"blueprint={_truncate(next_target.get('blueprint'), 320)}" if next_target.get("blueprint") else "",
                f"summary={_truncate(next_target.get('summary'), 260)}" if next_target.get("summary") else "",
            ]
            if item
        )
        lines.append(
            "- Next unit: "
            + _truncate(f"#{int(next_target.get('order_index') or 0) + 1} {next_target.get('title')}: {detail}", 760)
        )

    latest = workflow.get("latest_content_chapter")
    if isinstance(latest, dict):
        lines.append(
            "- Latest written unit: "
            + _truncate(f"#{int(latest.get('order_index') or 0) + 1} {latest.get('title')} [{latest.get('status')}]", 220)
        )
        if latest.get("content_tail"):
            lines.append("Previous unit ending / latest tail:\n" + _truncate(latest.get("content_tail"), 1200))

    next_planned = workflow.get("next_planned_chapter")
    if isinstance(next_planned, dict):
        lines.append(
            "- Next planned unit: "
            + _truncate(f"#{int(next_planned.get('order_index') or 0) + 1} {next_planned.get('title')}: {next_planned.get('plan')}", 700)
        )

    recent_lines: list[str] = []
    for row in workflow.get("recent_summaries") or []:
        if not isinstance(row, dict):
            continue
        detail = " | ".join(
            item
            for item in [
                f"summary={_truncate(row.get('summary'), 260)}" if row.get("summary") else "",
                f"notes={_truncate(row.get('continuity_notes'), 220)}" if row.get("continuity_notes") else "",
            ]
            if item
        )
        if detail:
            recent_lines.append(f"- #{int(row.get('order_index') or 0) + 1} {row.get('title')}: {detail}")
    if recent_lines:
        lines.append("Recent unit summaries / state updates:\n" + "\n".join(recent_lines))

    planned_lines: list[str] = []
    for row in workflow.get("planned_chapters") or []:
        if not isinstance(row, dict):
            continue
        detail = " | ".join(
            item
            for item in [
                f"plan={_truncate(row.get('plan'), 260)}" if row.get("plan") else "",
                f"blueprint={_truncate(row.get('blueprint'), 260)}" if row.get("blueprint") else "",
            ]
            if item
        )
        if detail:
            planned_lines.append(f"- #{int(row.get('order_index') or 0) + 1} {row.get('title')}: {detail}")
    if planned_lines:
        lines.append("Planned unit queue:\n" + "\n".join(planned_lines))

    chapter_lines: list[str] = []
    for row in workflow.get("chapters") or []:
        if not isinstance(row, dict):
            continue
        detail = " | ".join(
            item
            for item in [
                f"status={row.get('status')}",
                f"blueprint={_truncate(row.get('blueprint'), 260)}" if row.get("blueprint") else "",
                f"plan={_truncate(row.get('plan'), 240)}" if row.get("plan") else "",
                f"summary={_truncate(row.get('summary'), 240)}" if row.get("summary") else "",
                f"notes={_truncate(row.get('continuity_notes'), 220)}" if row.get("continuity_notes") else "",
            ]
            if item
        )
        if detail:
            chapter_lines.append(f"- #{int(row.get('order_index') or 0) + 1} {row.get('title')}: {detail}")
    if chapter_lines:
        lines.append("Document unit plan / summary ledger:\n" + "\n".join(chapter_lines))

    contract = workflow.get("execution_contract")
    if isinstance(contract, list) and contract:
        lines.append("Workflow execution contract:\n" + "\n".join(f"- {_truncate(item, 260)}" for item in contract))

    return "\n".join(lines)

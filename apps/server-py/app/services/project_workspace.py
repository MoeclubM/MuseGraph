from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectChapter,
    ProjectFact,
)
from app.services.project_files import project_workspace_root


def _workspace_metadata_dir(project_id: str) -> Path:
    target = project_workspace_root(project_id) / ".musegraph"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _workspace_documents_dir(project_id: str) -> Path:
    target = project_workspace_root(project_id) / "documents"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _workspace_facts_dir(project_id: str) -> Path:
    target = project_workspace_root(project_id) / "facts"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _chapter_document_path(project_id: str, chapter_id: str) -> Path:
    return _workspace_documents_dir(project_id) / f"{chapter_id}.md"


def _fact_file_path(project_id: str, fact_id: str) -> Path:
    return _workspace_facts_dir(project_id) / f"{fact_id}.json"


def _write_json(target: Path, payload: dict[str, Any] | list[Any]) -> None:
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _chapter_metadata(chapter: Any) -> dict[str, Any]:
    return {
        "id": chapter.id,
        "title": chapter.title,
        "status": chapter.status,
        "blueprint": chapter.blueprint,
        "plan": chapter.plan,
        "summary": chapter.summary,
        "continuity_notes": chapter.continuity_notes,
        "order_index": int(chapter.order_index),
    }


def _chapter_payload(chapter: Any) -> dict[str, Any]:
    payload = _chapter_metadata(chapter)
    payload["path"] = f"documents/{chapter.id}.md"
    return payload


def _fact_payload(fact: Any) -> dict[str, Any]:
    return {
        "id": fact.id,
        "project_id": fact.project_id,
        "created_by_user_id": fact.created_by_user_id,
        "created_by_agent_session_id": fact.created_by_agent_session_id,
        "source_kind": fact.source_kind,
        "source_ref": fact.source_ref,
        "title": fact.title,
        "content": fact.content,
        "metadata": fact.metadata_,
        "ontology_snapshot": fact.ontology_snapshot,
        "entities": fact.entities,
        "relationships": fact.relationships,
        "content_hash": fact.content_hash,
        "memory_status": fact.memory_status,
        "memory_task_id": fact.memory_task_id,
        "memory_error": fact.memory_error,
        "path": f"facts/{fact.id}.json",
    }


def _project_payload(
    project: Any,
    chapters: Iterable[Any],
    facts: Iterable[Any],
) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "visibility": project.visibility,
        "component_models": project.component_models,
        "operation_prompts": project.operation_prompts,
        "ontology_schema": project.ontology_schema,
        "creative_state": project.creative_state,
        "memory_id": project.memory_id,
        "chapters": [_chapter_payload(chapter) for chapter in sorted(chapters, key=lambda item: (item.order_index, item.id))],
        "facts": [
            _fact_payload(fact)
            for fact in sorted(facts, key=lambda item: (item.title, item.id))
        ],
    }


def write_project_manifest(
    project: Any,
    chapters: Iterable[Any],
    facts: Iterable[Any],
) -> dict[str, Any]:
    payload = _project_payload(project, chapters, facts)
    target = _workspace_metadata_dir(project.id) / "project.json"
    _write_json(target, payload)
    return payload


def write_project_chapter_document(project_id: str, chapter: Any) -> str:
    target = _chapter_document_path(project_id, chapter.id)
    metadata = _chapter_metadata(chapter)
    content = chapter.content
    text = (
        "---\n"
        f"{json.dumps(metadata, ensure_ascii=False, sort_keys=True)}\n"
        "---\n\n"
        f"{content}\n"
    )
    target.write_text(text, encoding="utf-8")
    return target.relative_to(project_workspace_root(project_id)).as_posix()


def write_project_fact_file(project_id: str, fact: Any) -> str:
    target = _fact_file_path(project_id, fact.id)
    payload = _fact_payload(fact)
    payload.pop("path")
    _write_json(target, payload)
    return target.relative_to(project_workspace_root(project_id)).as_posix()


def delete_project_chapter_document(project_id: str, chapter_id: str) -> None:
    target = _chapter_document_path(project_id, chapter_id)
    target.unlink()


def delete_project_fact_file(project_id: str, fact_id: str) -> None:
    target = _fact_file_path(project_id, fact_id)
    target.unlink()


def clear_project_workspace_snapshot(project_id: str) -> None:
    workspace = project_workspace_root(project_id)
    workspace.mkdir(parents=True, exist_ok=True)
    for name in (".musegraph", "documents", "facts"):
        target = (workspace / name).resolve()
        target.relative_to(workspace)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def write_project_workspace_snapshot(
    project: Any,
    chapters: Iterable[Any],
    facts: Iterable[Any],
) -> dict[str, Any]:
    ordered = sorted(chapters, key=lambda item: (item.order_index, item.id))
    ordered_facts = sorted(facts, key=lambda item: (item.title, item.id))
    payload = write_project_manifest(project, ordered, ordered_facts)
    for chapter in ordered:
        write_project_chapter_document(project.id, chapter)
    for fact in ordered_facts:
        write_project_fact_file(project.id, fact)
    return payload


def write_project_workspace_version_snapshot(
    project: Any,
    chapters: Iterable[Any],
    facts: Iterable[Any],
    message: str,
) -> dict[str, Any]:
    payload = write_project_workspace_snapshot(project, chapters, facts)
    from app.services.project_git import (
        commit_project_git,
        ensure_project_git_repo,
        push_project_git_branch,
        stage_project_git_paths,
    )

    ensure_project_git_repo(project.id)
    stage_project_git_paths(project.id)
    snapshot = commit_project_git(project.id, message)
    push_project_git_branch(project.id, "origin", snapshot["branch"])
    return payload


async def write_project_workspace_snapshot_from_db(project: Any, db: AsyncSession) -> dict[str, Any]:
    project_id = project.id

    async def _items(attr: str, model: Any) -> list[Any]:
        loaded = getattr(project, "__dict__", {}).get(attr)
        if loaded is not None:
            return list(loaded)
        return (await db.execute(select(model).where(model.project_id == project_id))).scalars().all()

    chapters = await _items("chapters", ProjectChapter)
    facts = await _items("facts", ProjectFact)
    return write_project_workspace_snapshot(project, chapters, facts)


async def write_project_workspace_version_snapshot_from_db(
    project: Any,
    db: AsyncSession,
    message: str,
) -> dict[str, Any]:
    project_id = project.id

    async def _items(attr: str, model: Any) -> list[Any]:
        loaded = getattr(project, "__dict__", {}).get(attr)
        if loaded is not None:
            return list(loaded)
        return (await db.execute(select(model).where(model.project_id == project_id))).scalars().all()

    chapters = await _items("chapters", ProjectChapter)
    facts = await _items("facts", ProjectFact)
    # File rewrites + dulwich stage/commit/push are synchronous IO; keep them off
    # the event loop so agent SSE streaming stays responsive.
    return await asyncio.to_thread(
        write_project_workspace_version_snapshot,
        project,
        chapters,
        facts,
        message,
    )

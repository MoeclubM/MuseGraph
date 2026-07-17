from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectChapter,
    ProjectFact,
    TextProject,
)
from app.services.project_git import (
    commit_project_git,
    list_project_record_points,
    push_project_git_branch,
    read_project_record_point_snapshot,
    stage_project_git_paths,
)
from app.services.project_workspace import clear_project_workspace_snapshot, write_project_workspace_snapshot


async def _project_items(project: TextProject, db: AsyncSession, attr: str, model: Any) -> list[Any]:
    loaded = getattr(project, "__dict__", {}).get(attr)
    if loaded is not None:
        return list(loaded)
    result = await db.execute(select(model).where(model.project_id == project.id))
    return list(result.scalars().all())


async def restore_project_record_point(
    project: TextProject,
    db: AsyncSession,
    record_point_id: str,
) -> dict[str, Any]:
    snapshot = read_project_record_point_snapshot(project.id, record_point_id)
    manifest = snapshot["manifest"]
    documents = snapshot["documents"]

    project.title = manifest["title"]
    project.description = manifest["description"]
    project.visibility = manifest["visibility"]
    project.component_models = manifest["component_models"]
    project.operation_prompts = manifest["operation_prompts"]
    project.ontology_schema = manifest["ontology_schema"]
    project.creative_state = manifest["creative_state"]
    project.memory_id = manifest["memory_id"]

    existing_chapters = await _project_items(project, db, "chapters", ProjectChapter)
    existing_facts = await _project_items(project, db, "facts", ProjectFact)

    chapters_by_id = {item.id: item for item in existing_chapters}
    facts_by_id = {item.id: item for item in existing_facts}

    restored_chapters: list[ProjectChapter] = []
    for item in manifest["chapters"]:
        chapter = chapters_by_id.get(item["id"])
        if chapter is None:
            chapter = ProjectChapter(id=item["id"], project_id=project.id)
            db.add(chapter)
        chapter.title = item["title"]
        chapter.status = item["status"]
        chapter.blueprint = item["blueprint"]
        chapter.plan = item["plan"]
        chapter.summary = item["summary"]
        chapter.continuity_notes = item["continuity_notes"]
        chapter.order_index = int(item["order_index"])
        chapter.content = documents[item["id"]]
        restored_chapters.append(chapter)

    restored_facts: list[ProjectFact] = []
    for item in manifest["facts"]:
        fact = facts_by_id.get(item["id"])
        if fact is None:
            fact = ProjectFact(id=item["id"], project_id=project.id)
            db.add(fact)
        fact.created_by_user_id = item["created_by_user_id"]
        fact.created_by_agent_session_id = item["created_by_agent_session_id"]
        fact.source_kind = item["source_kind"]
        fact.source_ref = item["source_ref"]
        fact.title = item["title"]
        fact.content = item["content"]
        fact.metadata_ = item["metadata"]
        fact.ontology_snapshot = item["ontology_snapshot"]
        fact.entities = item["entities"]
        fact.relationships = item["relationships"]
        fact.content_hash = item["content_hash"]
        fact.memory_status = item["memory_status"]
        fact.memory_task_id = item["memory_task_id"]
        fact.memory_error = item["memory_error"]
        restored_facts.append(fact)

    for item in existing_chapters:
        if item.id not in {chapter.id for chapter in restored_chapters}:
            await db.delete(item)
    for item in existing_facts:
        if item.id not in {fact.id for fact in restored_facts}:
            await db.delete(item)

    await db.flush()
    clear_project_workspace_snapshot(project.id)
    write_project_workspace_snapshot(
        project,
        restored_chapters,
        restored_facts,
    )
    stage_project_git_paths(project.id)
    snapshot_after_commit = commit_project_git(project.id, f"Restore record point {record_point_id[:7]}")
    push_project_git_branch(project.id, "origin", snapshot_after_commit["branch"])
    await db.commit()
    return list_project_record_points(project.id)

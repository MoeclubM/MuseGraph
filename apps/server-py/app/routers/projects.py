import asyncio
import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import (
    ProjectChapter,
    ProjectCharacter,
    ProjectGlossaryTerm,
    ProjectWorldbookEntry,
    TextOperation,
    TextProject,
)
from app.models.user import User
from app.schemas.project import (
    OperationRequest,
    OperationResponse,
    ProjectCharacterCreate,
    ProjectCharacterResponse,
    ProjectCharacterUpdate,
    ProjectGlossaryTermCreate,
    ProjectGlossaryTermResponse,
    ProjectGlossaryTermUpdate,
    ProjectChapterCreate,
    ProjectChapterReorderRequest,
    ProjectChapterResponse,
    ProjectChapterUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    ProjectWorldbookEntryCreate,
    ProjectWorldbookEntryResponse,
    ProjectWorldbookEntryUpdate,
)
from app.services.ai import (
    component_key_for_operation,
    resolve_component_model,
    run_operation,
    run_operation_async,
)
from app.services.task_state import TaskStatus, task_manager

router = APIRouter()


async def _get_project_for_user(project_id: str, user: User, db: AsyncSession) -> TextProject:
    result = await db.execute(
        select(TextProject)
        .where(TextProject.id == project_id)
        .options(
            selectinload(TextProject.chapters),
            selectinload(TextProject.characters),
            selectinload(TextProject.glossary_terms),
            selectinload(TextProject.worldbook_entries),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return project


def _sorted_chapters(project: TextProject) -> list[ProjectChapter]:
    # Avoid implicit async lazy-load here (can raise MissingGreenlet).
    chapters = project.__dict__.get("chapters") or []
    return sorted(chapters, key=lambda c: (c.order_index, c.created_at, c.id))


def _sorted_characters(project: TextProject) -> list[ProjectCharacter]:
    # Avoid implicit async lazy-load here (can raise MissingGreenlet).
    characters = project.__dict__.get("characters") or []
    return sorted(characters, key=lambda c: (c.order_index, c.created_at, c.id))


def _sorted_glossary_terms(project: TextProject) -> list[ProjectGlossaryTerm]:
    glossary_terms = project.__dict__.get("glossary_terms") or []
    return sorted(glossary_terms, key=lambda item: (item.order_index, item.created_at, item.id))


def _sorted_worldbook_entries(project: TextProject) -> list[ProjectWorldbookEntry]:
    worldbook_entries = project.__dict__.get("worldbook_entries") or []
    return sorted(worldbook_entries, key=lambda item: (item.order_index, item.created_at, item.id))


async def _ensure_default_chapter(project: TextProject, db: AsyncSession) -> ProjectChapter:
    chapters = _sorted_chapters(project)
    if chapters:
        return chapters[0]

    chapter = ProjectChapter(
        project_id=project.id,
        title="Main Draft",
        content="",
        order_index=0,
    )
    db.add(chapter)
    await db.flush()
    await db.refresh(project, attribute_names=["chapters"])
    return chapter


async def _realign_chapter_orders(project: TextProject, db: AsyncSession) -> None:
    changed = False
    for index, chapter in enumerate(_sorted_chapters(project)):
        if chapter.order_index != index:
            chapter.order_index = index
            changed = True
    if changed:
        await db.flush()


async def _realign_character_orders(project: TextProject, db: AsyncSession) -> None:
    changed = False
    for index, character in enumerate(_sorted_characters(project)):
        if character.order_index != index:
            character.order_index = index
            changed = True
    if changed:
        await db.flush()


async def _realign_glossary_term_orders(project: TextProject, db: AsyncSession) -> None:
    changed = False
    for index, item in enumerate(_sorted_glossary_terms(project)):
        if item.order_index != index:
            item.order_index = index
            changed = True
    if changed:
        await db.flush()


async def _realign_worldbook_entry_orders(project: TextProject, db: AsyncSession) -> None:
    changed = False
    for index, item in enumerate(_sorted_worldbook_entries(project)):
        if item.order_index != index:
            item.order_index = index
            changed = True
    if changed:
        await db.flush()


def _normalize_id_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _normalize_chapter_ids(chapter_ids: list[str] | None) -> list[str]:
    return _normalize_id_list(chapter_ids)


def _normalize_character_ids(character_ids: list[str] | None) -> list[str]:
    return _normalize_id_list(character_ids)


def _normalize_glossary_term_ids(glossary_term_ids: list[str] | None) -> list[str]:
    return _normalize_id_list(glossary_term_ids)


def _normalize_worldbook_entry_ids(worldbook_entry_ids: list[str] | None) -> list[str]:
    return _normalize_id_list(worldbook_entry_ids)


def _build_project_sync_idempotency_key(
    *,
    project_id: str,
    source_kind: str,
    action: str,
    entity_id: str | None,
    extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "project_id": str(project_id or "").strip(),
        "source_kind": str(source_kind or "").strip().lower(),
        "action": str(action or "").strip().lower(),
        "entity_id": str(entity_id or "").strip(),
        "extra": extra or {},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"project_sync:{fingerprint[:24]}"


def _record_project_sync_task(
    *,
    project_id: str,
    user_id: str,
    source_kind: str,
    action: str,
    entity_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    normalized_source = str(source_kind or "").strip().lower() or "project"
    normalized_action = str(action or "").strip().lower() or "update"
    idempotency_key = _build_project_sync_idempotency_key(
        project_id=project_id,
        source_kind=normalized_source,
        action=normalized_action,
        entity_id=entity_id,
        extra=extra,
    )
    existing = task_manager.find_inflight_task_by_idempotency(
        task_type="project_sync",
        project_id=project_id,
        idempotency_key=idempotency_key,
        max_age_minutes=2,
    )
    if existing is not None:
        return

    metadata: dict[str, Any] = {
        "project_id": project_id,
        "user_id": user_id,
        "source_kind": normalized_source,
        "action": normalized_action,
        "entity_id": str(entity_id or "").strip() or None,
        "sync_targets": ["graph", "rag"],
        "auto_created": True,
        "idempotency_key": idempotency_key,
    }
    if extra:
        metadata["extra"] = extra

    task = task_manager.create_task("project_sync", metadata=metadata)
    progress_detail: dict[str, Any] = {
        "stage": "sync_event",
        "step": f"{normalized_source}:{normalized_action}",
        "processed": 1,
        "total": 1,
        "source_kind": normalized_source,
        "action": normalized_action,
    }
    if entity_id:
        progress_detail["entity_id"] = entity_id
    task_manager.update_task(
        task.task_id,
        status=TaskStatus.PROCESSING,
        progress=50,
        message="Recording project sync event...",
        progress_detail=progress_detail,
    )
    task_manager.complete_task(
        task.task_id,
        result={
            "source_kind": normalized_source,
            "action": normalized_action,
            "entity_id": str(entity_id or "").strip() or None,
            "extra": extra or {},
        },
        message=f"Recorded {normalized_source} {normalized_action} sync event",
    )


def _trim_text(value: str | None, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)] + "..."


def _build_character_context(characters: list[ProjectCharacter]) -> str:
    if not characters:
        return ""
    lines: list[str] = []
    for index, character in enumerate(characters[:20], start=1):
        lines.append(f"{index}. Name: {_trim_text(character.name, 255)}")
        role = _trim_text(character.role, 255)
        if role:
            lines.append(f"   Role: {role}")
        profile = _trim_text(character.profile, 1200)
        if profile:
            lines.append(f"   Profile: {profile}")
        notes = _trim_text(character.notes, 800)
        if notes:
            lines.append(f"   Notes: {notes}")
    return "\n".join(lines).strip()


def _build_glossary_context(glossary_terms: list[ProjectGlossaryTerm]) -> str:
    if not glossary_terms:
        return ""
    lines: list[str] = []
    for index, term in enumerate(glossary_terms[:40], start=1):
        lines.append(f"{index}. Term: {_trim_text(term.term, 255)}")
        aliases = term.aliases if isinstance(term.aliases, list) else []
        alias_values = [str(alias).strip() for alias in aliases if str(alias or "").strip()]
        if alias_values:
            lines.append(f"   Aliases: {_trim_text(', '.join(alias_values), 800)}")
        definition = _trim_text(term.definition, 1200)
        if definition:
            lines.append(f"   Definition: {definition}")
        notes = _trim_text(term.notes, 800)
        if notes:
            lines.append(f"   Notes: {notes}")
    return "\n".join(lines).strip()


def _build_worldbook_context(entries: list[ProjectWorldbookEntry]) -> str:
    if not entries:
        return ""
    lines: list[str] = []
    for index, entry in enumerate(entries[:40], start=1):
        lines.append(f"{index}. Title: {_trim_text(entry.title, 255)}")
        category = _trim_text(entry.category, 120)
        if category:
            lines.append(f"   Category: {category}")
        tags = entry.tags if isinstance(entry.tags, list) else []
        tag_values = [str(tag).strip() for tag in tags if str(tag or "").strip()]
        if tag_values:
            lines.append(f"   Tags: {_trim_text(', '.join(tag_values), 800)}")
        content = _trim_text(entry.content, 1400)
        if content:
            lines.append(f"   Content: {content}")
        notes = _trim_text(entry.notes, 800)
        if notes:
            lines.append(f"   Notes: {notes}")
    return "\n".join(lines).strip()


def _compose_reference_context(
    *,
    character_context: str,
    glossary_context: str,
    worldbook_context: str,
) -> str:
    sections: list[str] = []
    if character_context:
        sections.append(f"### Character Cards\n{character_context}")
    if glossary_context:
        sections.append(f"### Glossary Terms\n{glossary_context}")
    if worldbook_context:
        sections.append(f"### Worldbook Entries\n{worldbook_context}")
    return "\n\n".join(sections).strip()


def _build_reference_cards_payload(
    *,
    characters: list[ProjectCharacter],
    glossary_terms: list[ProjectGlossaryTerm],
    worldbook_entries: list[ProjectWorldbookEntry],
    explicit_character_ids: list[str],
    explicit_glossary_term_ids: list[str],
    explicit_worldbook_entry_ids: list[str],
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}

    if characters:
        payload["characters"] = [
            {
                "id": character.id,
                "name": character.name,
                "role": character.role,
                "profile": character.profile,
                "notes": character.notes,
                "order_index": int(character.order_index),
            }
            for character in characters
        ]
    if glossary_terms:
        payload["glossary_terms"] = [
            {
                "id": term.id,
                "term": term.term,
                "definition": term.definition,
                "aliases": term.aliases if isinstance(term.aliases, list) else [],
                "notes": term.notes,
                "order_index": int(term.order_index),
            }
            for term in glossary_terms
        ]
    if worldbook_entries:
        payload["worldbook_entries"] = [
            {
                "id": entry.id,
                "title": entry.title,
                "category": entry.category,
                "content": entry.content,
                "tags": entry.tags if isinstance(entry.tags, list) else [],
                "notes": entry.notes,
                "order_index": int(entry.order_index),
            }
            for entry in worldbook_entries
        ]

    if explicit_character_ids:
        payload["explicit_character_ids"] = explicit_character_ids
    if explicit_glossary_term_ids:
        payload["explicit_glossary_term_ids"] = explicit_glossary_term_ids
    if explicit_worldbook_entry_ids:
        payload["explicit_worldbook_entry_ids"] = explicit_worldbook_entry_ids

    return payload or None


async def _resolve_operation_characters(
    *,
    project: TextProject,
    character_ids: list[str] | None,
    db: AsyncSession,
) -> tuple[str, list[str], list[ProjectCharacter]]:
    normalized = _normalize_character_ids(character_ids)
    if normalized:
        result = await db.execute(
            select(ProjectCharacter).where(
                ProjectCharacter.project_id == project.id,
                ProjectCharacter.id.in_(normalized),
            )
        )
        rows = result.scalars().all()
        row_map = {row.id: row for row in rows}
        missing = [character_id for character_id in normalized if character_id not in row_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid character_ids for project: {', '.join(missing)}",
            )
        ordered = [row_map[character_id] for character_id in normalized]
        return _build_character_context(ordered), normalized, ordered

    characters = _sorted_characters(project)
    return _build_character_context(characters), [], characters


async def _resolve_operation_glossary_terms(
    *,
    project: TextProject,
    glossary_term_ids: list[str] | None,
    db: AsyncSession,
) -> tuple[str, list[str], list[ProjectGlossaryTerm]]:
    normalized = _normalize_glossary_term_ids(glossary_term_ids)
    if normalized:
        result = await db.execute(
            select(ProjectGlossaryTerm).where(
                ProjectGlossaryTerm.project_id == project.id,
                ProjectGlossaryTerm.id.in_(normalized),
            )
        )
        rows = result.scalars().all()
        row_map = {row.id: row for row in rows}
        missing = [item_id for item_id in normalized if item_id not in row_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid glossary_term_ids for project: {', '.join(missing)}",
            )
        ordered = [row_map[item_id] for item_id in normalized]
        return _build_glossary_context(ordered), normalized, ordered
    glossary_terms = _sorted_glossary_terms(project)
    return _build_glossary_context(glossary_terms), [], glossary_terms


async def _resolve_operation_worldbook_entries(
    *,
    project: TextProject,
    worldbook_entry_ids: list[str] | None,
    db: AsyncSession,
) -> tuple[str, list[str], list[ProjectWorldbookEntry]]:
    normalized = _normalize_worldbook_entry_ids(worldbook_entry_ids)
    if normalized:
        result = await db.execute(
            select(ProjectWorldbookEntry).where(
                ProjectWorldbookEntry.project_id == project.id,
                ProjectWorldbookEntry.id.in_(normalized),
            )
        )
        rows = result.scalars().all()
        row_map = {row.id: row for row in rows}
        missing = [item_id for item_id in normalized if item_id not in row_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid worldbook_entry_ids for project: {', '.join(missing)}",
            )
        ordered = [row_map[item_id] for item_id in normalized]
        return _build_worldbook_context(ordered), normalized, ordered
    worldbook_entries = _sorted_worldbook_entries(project)
    return _build_worldbook_context(worldbook_entries), [], worldbook_entries


async def _resolve_operation_input(
    *,
    project: TextProject,
    chapter_ids: list[str] | None,
    provided_input: str | None,
    db: AsyncSession,
) -> tuple[str, list[str]]:
    normalized = _normalize_chapter_ids(chapter_ids)
    if normalized:
        result = await db.execute(
            select(ProjectChapter).where(
                ProjectChapter.project_id == project.id,
                ProjectChapter.id.in_(normalized),
            )
        )
        chapters = result.scalars().all()
        chapter_map = {chapter.id: chapter for chapter in chapters}
        missing = [chapter_id for chapter_id in normalized if chapter_id not in chapter_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid chapter_ids for project: {', '.join(missing)}",
            )
        chapters = sorted(chapters, key=lambda c: (c.order_index, c.created_at, c.id))
        merged = "\n\n".join((chapter.content or "").strip() for chapter in chapters if chapter.content is not None).strip()
        if provided_input and provided_input.strip():
            merged = f"{provided_input.strip()}\n\n{merged}" if merged else provided_input.strip()
        if not merged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected chapters have no text content",
            )
        return merged, [chapter.id for chapter in chapters]

    chapters = _sorted_chapters(project)
    chapter_text = "\n\n".join((chapter.content or "").strip() for chapter in chapters if chapter.content is not None).strip()
    text = (provided_input or "").strip() or chapter_text
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no text content",
        )
    return text, []


def _project_has_text_content(project: TextProject) -> bool:
    for chapter in _sorted_chapters(project):
        if str(chapter.content or "").strip():
            return True
    return False


def _resolve_operation_use_rag(op_type: str, requested_use_rag: bool | None) -> bool:
    # CREATE supports explicit no-RAG generation (outline stage).
    if op_type == "CREATE":
        if requested_use_rag is None:
            return True
        return bool(requested_use_rag)
    # CONTINUE/ANALYZE/REWRITE/SUMMARIZE always keep RAG enabled.
    return True


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    result = await db.execute(
        select(TextProject)
        .where(TextProject.user_id == user.id)
        .options(selectinload(TextProject.chapters))
        .order_by(TextProject.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    projects = result.scalars().all()
    return [ProjectResponse.model_validate(p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = TextProject(
        user_id=user.id,
        title=body.title,
        description=body.description,
        simulation_requirement=body.simulation_requirement,
        component_models=body.component_models,
    )
    db.add(project)
    await db.flush()
    await _ensure_default_chapter(project, db)
    await db.refresh(project)
    await db.refresh(project, attribute_names=["chapters"])
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    return ProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if body.title is not None:
        project.title = body.title
    if body.description is not None:
        project.description = body.description
    if body.simulation_requirement is not None:
        project.simulation_requirement = body.simulation_requirement
    if body.component_models is not None:
        project.component_models = body.component_models
    if body.oasis_analysis is not None:
        project.oasis_analysis = body.oasis_analysis

    await db.flush()
    await db.refresh(project)
    await db.refresh(project, attribute_names=["chapters"])
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    await db.delete(project)
    return None


@router.get("/{project_id}/chapters", response_model=list[ProjectChapterResponse])
async def list_project_chapters(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not _sorted_chapters(project):
        await _ensure_default_chapter(project, db)
        await _realign_chapter_orders(project, db)
        await db.refresh(project, attribute_names=["chapters"])

    return [ProjectChapterResponse.model_validate(chapter) for chapter in _sorted_chapters(project)]


@router.post("/{project_id}/chapters", response_model=ProjectChapterResponse, status_code=status.HTTP_201_CREATED)
async def create_project_chapter(
    project_id: str,
    body: ProjectChapterCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    chapters = _sorted_chapters(project)
    next_index = len(chapters) if body.order_index is None else min(max(body.order_index, 0), len(chapters))

    for chapter in chapters:
        if chapter.order_index >= next_index:
            chapter.order_index += 1

    chapter = ProjectChapter(
        project_id=project.id,
        title=(body.title or "Main Draft").strip() or "Main Draft",
        content=body.content or "",
        order_index=next_index,
    )
    db.add(chapter)
    await db.flush()

    await db.refresh(project, attribute_names=["chapters"])
    await _realign_chapter_orders(project, db)
    await db.refresh(project, attribute_names=["chapters"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="chapter",
        action="create",
        entity_id=chapter.id,
        extra={"chapter_ids": [chapter.id]},
    )
    return ProjectChapterResponse.model_validate(chapter)


@router.put("/{project_id}/chapters/{chapter_id}", response_model=ProjectChapterResponse)
async def update_project_chapter(
    project_id: str,
    chapter_id: str,
    body: ProjectChapterUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target = next((chapter for chapter in _sorted_chapters(project) if chapter.id == chapter_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")

    if body.title is not None:
        target.title = body.title.strip() or target.title
    if body.content is not None:
        target.content = body.content

    if body.order_index is not None:
        chapters = _sorted_chapters(project)
        chapters_without_target = [chapter for chapter in chapters if chapter.id != chapter_id]
        new_index = min(max(body.order_index, 0), len(chapters_without_target))
        reordered = chapters_without_target[:new_index] + [target] + chapters_without_target[new_index:]
        for idx, chapter in enumerate(reordered):
            chapter.order_index = idx

    await db.flush()
    await db.refresh(project, attribute_names=["chapters"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="chapter",
        action="update",
        entity_id=target.id,
        extra={"chapter_ids": [target.id]},
    )

    return ProjectChapterResponse.model_validate(target)


@router.delete("/{project_id}/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_chapter(
    project_id: str,
    chapter_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    chapters = _sorted_chapters(project)
    if len(chapters) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one chapter must be kept")

    target = next((chapter for chapter in chapters if chapter.id == chapter_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")

    await db.delete(target)
    await db.flush()
    await db.refresh(project, attribute_names=["chapters"])
    await _realign_chapter_orders(project, db)
    await db.refresh(project, attribute_names=["chapters"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="chapter",
        action="delete",
        entity_id=target.id,
        extra={"chapter_ids": [target.id]},
    )
    return None


@router.post("/{project_id}/chapters/reorder", response_model=list[ProjectChapterResponse])
async def reorder_project_chapters(
    project_id: str,
    body: ProjectChapterReorderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    chapters = _sorted_chapters(project)
    existing_ids = {chapter.id for chapter in chapters}
    payload_ids = {item.id for item in body.chapters}
    if existing_ids != payload_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reorder payload must include all project chapters")

    mapping = {item.id: item.order_index for item in body.chapters}
    for chapter in chapters:
        chapter.order_index = mapping[chapter.id]

    await db.flush()
    await db.refresh(project, attribute_names=["chapters"])
    await _realign_chapter_orders(project, db)
    await db.refresh(project, attribute_names=["chapters"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="chapter",
        action="reorder",
        extra={"chapter_ids": sorted(existing_ids)},
    )

    return [ProjectChapterResponse.model_validate(chapter) for chapter in _sorted_chapters(project)]


@router.get("/{project_id}/characters", response_model=list[ProjectCharacterResponse])
async def list_project_characters(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return [ProjectCharacterResponse.model_validate(character) for character in _sorted_characters(project)]


@router.post("/{project_id}/characters", response_model=ProjectCharacterResponse, status_code=status.HTTP_201_CREATED)
async def create_project_character(
    project_id: str,
    body: ProjectCharacterCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    characters = _sorted_characters(project)
    next_index = len(characters) if body.order_index is None else min(max(body.order_index, 0), len(characters))
    for character in characters:
        if character.order_index >= next_index:
            character.order_index += 1

    character = ProjectCharacter(
        project_id=project.id,
        name=body.name.strip(),
        role=(body.role or "").strip() or None,
        profile=body.profile,
        notes=body.notes,
        order_index=next_index,
    )
    db.add(character)
    await db.flush()

    await db.refresh(project, attribute_names=["characters"])
    await _realign_character_orders(project, db)
    await db.refresh(project, attribute_names=["characters"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="character",
        action="create",
        entity_id=character.id,
        extra={"character_ids": [character.id]},
    )
    return ProjectCharacterResponse.model_validate(character)


@router.put("/{project_id}/characters/{character_id}", response_model=ProjectCharacterResponse)
async def update_project_character(
    project_id: str,
    character_id: str,
    body: ProjectCharacterUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target = next((character for character in _sorted_characters(project) if character.id == character_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    if body.name is not None:
        target.name = body.name.strip() or target.name
    if body.role is not None:
        target.role = body.role.strip() or None
    if body.profile is not None:
        target.profile = body.profile
    if body.notes is not None:
        target.notes = body.notes

    if body.order_index is not None:
        characters = _sorted_characters(project)
        without_target = [character for character in characters if character.id != character_id]
        new_index = min(max(body.order_index, 0), len(without_target))
        reordered = without_target[:new_index] + [target] + without_target[new_index:]
        for idx, character in enumerate(reordered):
            character.order_index = idx

    await db.flush()
    await db.refresh(project, attribute_names=["characters"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="character",
        action="update",
        entity_id=target.id,
        extra={"character_ids": [target.id]},
    )
    return ProjectCharacterResponse.model_validate(target)


@router.delete("/{project_id}/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_character(
    project_id: str,
    character_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target = next((character for character in _sorted_characters(project) if character.id == character_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    await db.delete(target)
    await db.flush()
    await db.refresh(project, attribute_names=["characters"])
    await _realign_character_orders(project, db)
    await db.refresh(project, attribute_names=["characters"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="character",
        action="delete",
        entity_id=target.id,
        extra={"character_ids": [target.id]},
    )
    return None


@router.get("/{project_id}/glossary-terms", response_model=list[ProjectGlossaryTermResponse])
async def list_project_glossary_terms(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return [ProjectGlossaryTermResponse.model_validate(item) for item in _sorted_glossary_terms(project)]


@router.post("/{project_id}/glossary-terms", response_model=ProjectGlossaryTermResponse, status_code=status.HTTP_201_CREATED)
async def create_project_glossary_term(
    project_id: str,
    body: ProjectGlossaryTermCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    glossary_terms = _sorted_glossary_terms(project)
    next_index = len(glossary_terms) if body.order_index is None else min(max(body.order_index, 0), len(glossary_terms))
    for item in glossary_terms:
        if item.order_index >= next_index:
            item.order_index += 1

    term = ProjectGlossaryTerm(
        project_id=project.id,
        term=body.term.strip(),
        definition=(body.definition or "").strip(),
        aliases=body.aliases or None,
        notes=body.notes,
        order_index=next_index,
    )
    db.add(term)
    await db.flush()

    await db.refresh(project, attribute_names=["glossary_terms"])
    await _realign_glossary_term_orders(project, db)
    await db.refresh(project, attribute_names=["glossary_terms"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="glossary_term",
        action="create",
        entity_id=term.id,
        extra={"glossary_term_ids": [term.id]},
    )
    return ProjectGlossaryTermResponse.model_validate(term)


@router.put("/{project_id}/glossary-terms/{term_id}", response_model=ProjectGlossaryTermResponse)
async def update_project_glossary_term(
    project_id: str,
    term_id: str,
    body: ProjectGlossaryTermUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target = next((item for item in _sorted_glossary_terms(project) if item.id == term_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Glossary term not found")

    if body.term is not None:
        target.term = body.term.strip() or target.term
    if body.definition is not None:
        target.definition = body.definition
    if body.aliases is not None:
        target.aliases = body.aliases or None
    if body.notes is not None:
        target.notes = body.notes

    if body.order_index is not None:
        glossary_terms = _sorted_glossary_terms(project)
        without_target = [item for item in glossary_terms if item.id != term_id]
        new_index = min(max(body.order_index, 0), len(without_target))
        reordered = without_target[:new_index] + [target] + without_target[new_index:]
        for idx, item in enumerate(reordered):
            item.order_index = idx

    await db.flush()
    await db.refresh(project, attribute_names=["glossary_terms"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="glossary_term",
        action="update",
        entity_id=target.id,
        extra={"glossary_term_ids": [target.id]},
    )
    return ProjectGlossaryTermResponse.model_validate(target)


@router.delete("/{project_id}/glossary-terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_glossary_term(
    project_id: str,
    term_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target = next((item for item in _sorted_glossary_terms(project) if item.id == term_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Glossary term not found")

    await db.delete(target)
    await db.flush()
    await db.refresh(project, attribute_names=["glossary_terms"])
    await _realign_glossary_term_orders(project, db)
    await db.refresh(project, attribute_names=["glossary_terms"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="glossary_term",
        action="delete",
        entity_id=target.id,
        extra={"glossary_term_ids": [target.id]},
    )
    return None


@router.get("/{project_id}/worldbook-entries", response_model=list[ProjectWorldbookEntryResponse])
async def list_project_worldbook_entries(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return [ProjectWorldbookEntryResponse.model_validate(item) for item in _sorted_worldbook_entries(project)]


@router.post("/{project_id}/worldbook-entries", response_model=ProjectWorldbookEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_project_worldbook_entry(
    project_id: str,
    body: ProjectWorldbookEntryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    worldbook_entries = _sorted_worldbook_entries(project)
    next_index = len(worldbook_entries) if body.order_index is None else min(max(body.order_index, 0), len(worldbook_entries))
    for item in worldbook_entries:
        if item.order_index >= next_index:
            item.order_index += 1

    entry = ProjectWorldbookEntry(
        project_id=project.id,
        title=body.title.strip(),
        category=(body.category or "").strip() or None,
        content=(body.content or "").strip(),
        tags=body.tags or None,
        notes=body.notes,
        order_index=next_index,
    )
    db.add(entry)
    await db.flush()

    await db.refresh(project, attribute_names=["worldbook_entries"])
    await _realign_worldbook_entry_orders(project, db)
    await db.refresh(project, attribute_names=["worldbook_entries"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="worldbook_entry",
        action="create",
        entity_id=entry.id,
        extra={"worldbook_entry_ids": [entry.id]},
    )
    return ProjectWorldbookEntryResponse.model_validate(entry)


@router.put("/{project_id}/worldbook-entries/{entry_id}", response_model=ProjectWorldbookEntryResponse)
async def update_project_worldbook_entry(
    project_id: str,
    entry_id: str,
    body: ProjectWorldbookEntryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target = next((item for item in _sorted_worldbook_entries(project) if item.id == entry_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worldbook entry not found")

    if body.title is not None:
        target.title = body.title.strip() or target.title
    if body.category is not None:
        target.category = body.category.strip() or None
    if body.content is not None:
        target.content = body.content
    if body.tags is not None:
        target.tags = body.tags or None
    if body.notes is not None:
        target.notes = body.notes

    if body.order_index is not None:
        worldbook_entries = _sorted_worldbook_entries(project)
        without_target = [item for item in worldbook_entries if item.id != entry_id]
        new_index = min(max(body.order_index, 0), len(without_target))
        reordered = without_target[:new_index] + [target] + without_target[new_index:]
        for idx, item in enumerate(reordered):
            item.order_index = idx

    await db.flush()
    await db.refresh(project, attribute_names=["worldbook_entries"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="worldbook_entry",
        action="update",
        entity_id=target.id,
        extra={"worldbook_entry_ids": [target.id]},
    )
    return ProjectWorldbookEntryResponse.model_validate(target)


@router.delete("/{project_id}/worldbook-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_worldbook_entry(
    project_id: str,
    entry_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    target = next((item for item in _sorted_worldbook_entries(project) if item.id == entry_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worldbook entry not found")

    await db.delete(target)
    await db.flush()
    await db.refresh(project, attribute_names=["worldbook_entries"])
    await _realign_worldbook_entry_orders(project, db)
    await db.refresh(project, attribute_names=["worldbook_entries"])
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="worldbook_entry",
        action="delete",
        entity_id=target.id,
        extra={"worldbook_entry_ids": [target.id]},
    )
    return None


@router.post("/{project_id}/operation", response_model=OperationResponse)
async def create_operation(
    project_id: str,
    body: OperationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    op_type = (body.type or "").upper()
    if op_type not in {"CREATE", "CONTINUE", "ANALYZE", "REWRITE", "SUMMARIZE"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported operation type",
        )

    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if op_type == "CREATE":
        if _project_has_text_content(project):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CREATE is only allowed when the workspace is empty (0 text).",
            )
    elif not project.cognee_dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Knowledge graph is required before running operations.",
        )

    use_rag = _resolve_operation_use_rag(op_type, body.use_rag)

    model = resolve_component_model(
        project,
        component_key_for_operation(op_type),
        body.model,
    )
    source_input, source_chapter_ids = await _resolve_operation_input(
        project=project,
        chapter_ids=body.chapter_ids,
        provided_input=body.input,
        db=db,
    )
    character_context, source_character_ids, source_characters = await _resolve_operation_characters(
        project=project,
        character_ids=body.character_ids,
        db=db,
    )
    glossary_context, source_glossary_term_ids, source_glossary_terms = await _resolve_operation_glossary_terms(
        project=project,
        glossary_term_ids=body.glossary_term_ids,
        db=db,
    )
    worldbook_context, source_worldbook_entry_ids, source_worldbook_entries = await _resolve_operation_worldbook_entries(
        project=project,
        worldbook_entry_ids=body.worldbook_entry_ids,
        db=db,
    )
    reference_context = _compose_reference_context(
        character_context=character_context,
        glossary_context=glossary_context,
        worldbook_context=worldbook_context,
    )

    metadata: dict[str, list[str]] = {}
    if source_chapter_ids:
        metadata["source_chapter_ids"] = source_chapter_ids
    if source_character_ids:
        metadata["source_character_ids"] = source_character_ids
    if source_glossary_term_ids:
        metadata["source_glossary_term_ids"] = source_glossary_term_ids
    if source_worldbook_entry_ids:
        metadata["source_worldbook_entry_ids"] = source_worldbook_entry_ids

    reference_cards = _build_reference_cards_payload(
        characters=source_characters,
        glossary_terms=source_glossary_terms,
        worldbook_entries=source_worldbook_entries,
        explicit_character_ids=source_character_ids,
        explicit_glossary_term_ids=source_glossary_term_ids,
        explicit_worldbook_entry_ids=source_worldbook_entry_ids,
    )

    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=source_input,
        model=model,
        status="PENDING",
        metadata_=metadata or None,
    )
    db.add(operation)
    await db.flush()

    operation = await run_operation(
        operation.id,
        project,
        user,
        op_type,
        source_input,
        model,
        db,
        use_rag=use_rag,
        character_context=reference_context,
        reference_cards=reference_cards,
    )
    return OperationResponse.model_validate(operation)


@router.post("/{project_id}/operation/stream", response_model=OperationResponse)
async def create_operation_stream(
    project_id: str,
    body: OperationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create operation and process asynchronously. Use GET /operation/{op_id}/stream for SSE updates."""
    op_type = (body.type or "").upper()
    if op_type not in {"CREATE", "CONTINUE", "ANALYZE", "REWRITE", "SUMMARIZE"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported operation type",
        )

    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if op_type == "CREATE":
        if _project_has_text_content(project):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CREATE is only allowed when the workspace is empty (0 text).",
            )
    elif not project.cognee_dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Knowledge graph is required before running operations.",
        )

    use_rag = _resolve_operation_use_rag(op_type, body.use_rag)

    model = resolve_component_model(
        project,
        component_key_for_operation(op_type),
        body.model,
    )
    source_input, source_chapter_ids = await _resolve_operation_input(
        project=project,
        chapter_ids=body.chapter_ids,
        provided_input=body.input,
        db=db,
    )
    character_context, source_character_ids, source_characters = await _resolve_operation_characters(
        project=project,
        character_ids=body.character_ids,
        db=db,
    )
    glossary_context, source_glossary_term_ids, source_glossary_terms = await _resolve_operation_glossary_terms(
        project=project,
        glossary_term_ids=body.glossary_term_ids,
        db=db,
    )
    worldbook_context, source_worldbook_entry_ids, source_worldbook_entries = await _resolve_operation_worldbook_entries(
        project=project,
        worldbook_entry_ids=body.worldbook_entry_ids,
        db=db,
    )
    reference_context = _compose_reference_context(
        character_context=character_context,
        glossary_context=glossary_context,
        worldbook_context=worldbook_context,
    )

    metadata: dict[str, list[str]] = {}
    if source_chapter_ids:
        metadata["source_chapter_ids"] = source_chapter_ids
    if source_character_ids:
        metadata["source_character_ids"] = source_character_ids
    if source_glossary_term_ids:
        metadata["source_glossary_term_ids"] = source_glossary_term_ids
    if source_worldbook_entry_ids:
        metadata["source_worldbook_entry_ids"] = source_worldbook_entry_ids

    reference_cards = _build_reference_cards_payload(
        characters=source_characters,
        glossary_terms=source_glossary_terms,
        worldbook_entries=source_worldbook_entries,
        explicit_character_ids=source_character_ids,
        explicit_glossary_term_ids=source_glossary_term_ids,
        explicit_worldbook_entry_ids=source_worldbook_entry_ids,
    )

    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=source_input,
        model=model,
        status="PENDING",
        metadata_=metadata or None,
    )
    db.add(operation)
    await db.flush()

    asyncio.create_task(
        run_operation_async(
            operation.id,
            project_id,
            user.id,
            op_type,
            source_input,
            model,
            use_rag=use_rag,
            character_context=reference_context,
            reference_cards=reference_cards,
        )
    )

    return OperationResponse.model_validate(operation)


@router.get("/{project_id}/operation/{operation_id}/stream")
async def stream_operation(
    project_id: str,
    operation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint for operation progress."""
    import redis.asyncio as aioredis

    from app.config import settings as s

    project = await _get_project_for_user(project_id, user, db)
    if not project or (project.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    async def event_generator():
        sub_client = aioredis.from_url(s.REDIS_URL, decode_responses=True)
        pubsub = sub_client.pubsub()
        await pubsub.subscribe(f"operation:{operation_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield {"event": "progress", "data": json.dumps(data)}
                    if data.get("status") in ("COMPLETED", "FAILED"):
                        break
        finally:
            await pubsub.unsubscribe(f"operation:{operation_id}")
            await sub_client.aclose()

    return EventSourceResponse(event_generator())


@router.get("/{project_id}/operations", response_model=list[OperationResponse])
async def list_operations(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(TextOperation)
        .where(TextOperation.project_id == project_id)
        .order_by(TextOperation.created_at.desc())
    )
    operations = result.scalars().all()
    return [OperationResponse.model_validate(op) for op in operations]


ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".docx", ".pdf"}


def extract_text_from_file(filename: str, content: bytes) -> str:
    import os
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".txt", ".md"):
        return content.decode("utf-8")
    elif ext == ".docx":
        import io
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    elif ext == ".pdf":
        import io
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


@router.post("/{project_id}/operation/upload", response_model=OperationResponse)
async def create_operation_upload(
    project_id: str,
    file: UploadFile = File(...),
    type: str = Form(...),
    model: str = Form(None),
    chapter_ids: list[str] | None = Form(None),
    character_ids: list[str] | None = Form(None),
    glossary_term_ids: list[str] | None = Form(None),
    worldbook_entry_ids: list[str] | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    op_type = (type or "").upper()
    if op_type not in ("CONTINUE", "ANALYZE", "REWRITE", "SUMMARIZE"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File upload supports CONTINUE, ANALYZE, REWRITE, and SUMMARIZE operations",
        )

    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_UPLOAD_EXTENSIONS)}",
        )

    project = await _get_project_for_user(project_id, user, db)
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if not project.cognee_dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Knowledge graph is required before running operations.",
        )

    file_content = await file.read()

    # Store original file in persistent local storage for audit
    try:
        from app.storage import upload_file
        stored_name = f"uploads/{project_id}/{uuid.uuid4().hex}{ext}"
        upload_file(stored_name, file_content, file.content_type or "application/octet-stream")
    except Exception:
        pass  # Non-critical, continue even if storage fails

    # Extract text
    try:
        input_text = extract_text_from_file(file.filename or "file.txt", file_content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to extract text from file: {e}",
        )

    source_input, source_chapter_ids = await _resolve_operation_input(
        project=project,
        chapter_ids=chapter_ids,
        provided_input=input_text,
        db=db,
    )
    character_context, source_character_ids, source_characters = await _resolve_operation_characters(
        project=project,
        character_ids=character_ids,
        db=db,
    )
    glossary_context, source_glossary_term_ids, source_glossary_terms = await _resolve_operation_glossary_terms(
        project=project,
        glossary_term_ids=glossary_term_ids,
        db=db,
    )
    worldbook_context, source_worldbook_entry_ids, source_worldbook_entries = await _resolve_operation_worldbook_entries(
        project=project,
        worldbook_entry_ids=worldbook_entry_ids,
        db=db,
    )
    reference_context = _compose_reference_context(
        character_context=character_context,
        glossary_context=glossary_context,
        worldbook_context=worldbook_context,
    )
    use_model = resolve_component_model(
        project,
        component_key_for_operation(op_type),
        model,
    )

    metadata: dict[str, list[str]] = {}
    if source_chapter_ids:
        metadata["source_chapter_ids"] = source_chapter_ids
    if source_character_ids:
        metadata["source_character_ids"] = source_character_ids
    if source_glossary_term_ids:
        metadata["source_glossary_term_ids"] = source_glossary_term_ids
    if source_worldbook_entry_ids:
        metadata["source_worldbook_entry_ids"] = source_worldbook_entry_ids

    reference_cards = _build_reference_cards_payload(
        characters=source_characters,
        glossary_terms=source_glossary_terms,
        worldbook_entries=source_worldbook_entries,
        explicit_character_ids=source_character_ids,
        explicit_glossary_term_ids=source_glossary_term_ids,
        explicit_worldbook_entry_ids=source_worldbook_entry_ids,
    )

    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=source_input,
        model=use_model,
        status="PENDING",
        metadata_=metadata or None,
    )
    db.add(operation)
    await db.flush()

    operation = await run_operation(
        operation.id,
        project,
        user,
        op_type,
        source_input,
        use_model,
        db,
        character_context=reference_context,
        reference_cards=reference_cards,
    )
    return OperationResponse.model_validate(operation)

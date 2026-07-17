import hashlib
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session, get_db
from app.dependencies import get_current_user
from app.models.project import (
    ProjectChapter,
    ProjectFact,
    ProjectMember,
    TextProject,
)
from app.models.user import User
from app.schemas.project import (
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectChapterCreate,
    ProjectChapterReorderRequest,
    ProjectChapterResponse,
    ProjectChapterUpdate,
    ProjectCreate,
    ProjectPublicResponse,
    ProjectResponse,
    ProjectSearchResult,
    ProjectUpdate,
    ProjectVisibilityUpdate,
)
from app.services.project_access import (
    PROJECT_PERMISSION_DELETE,
    PROJECT_PERMISSION_EDIT,
    PROJECT_PERMISSION_MANAGE,
    PROJECT_PERMISSION_VIEW,
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_VIEWER,
    PROJECT_ROLE_OWNER,
    PROJECT_VISIBILITY_PUBLIC,
    accessible_projects_query,
    project_permissions_for_role,
    require_project_permission,
    validate_project_member_role,
    validate_project_visibility,
)
from app.services.ai import SUPPORTED_TEXT_OPERATION_TYPES
from app.services.agent.control_docs import seed_control_docs
from app.services.creative_workflow import chapter_has_memory_material, chapter_memory_text
from app.services.project_git import (
    commit_project_git,
    delete_project_git_storage,
    initialize_project_git_repo,
    push_project_git_branch,
    stage_project_git_paths,
)
from app.services.project_workspace import (
    delete_project_chapter_document,
    write_project_workspace_snapshot,
    write_project_workspace_version_snapshot,
)
from app.services.task_state import TaskStatus, task_manager

router = APIRouter()
MEMORY_AUTO_SYNC_COMPONENT_KEY = "memory_auto_sync"
MEMORY_AUTO_SYNC_DISABLED = "disabled"
OPERATION_PROMPT_KEYS = SUPPORTED_TEXT_OPERATION_TYPES


async def _get_project_for_user(
    project_id: str,
    user: User,
    db: AsyncSession,
    permission: str = PROJECT_PERMISSION_VIEW,
) -> TextProject:
    return await require_project_permission(
        project_id,
        user,
        db,
        permission,
        load_options=(
            selectinload(TextProject.chapters),
            selectinload(TextProject.facts),
        ),
    )


def _sorted_chapters(project: TextProject) -> list[ProjectChapter]:
    # Avoid implicit async lazy-load here (can raise MissingGreenlet).
    chapters = project.__dict__.get("chapters") or []
    return sorted(chapters, key=lambda c: (c.order_index, c.created_at, c.id))


def _sorted_facts(project: TextProject) -> list[ProjectFact]:
    facts = project.__dict__.get("facts") or []
    return sorted(facts, key=lambda item: (item.title, item.id))


def _write_project_workspace(project: TextProject) -> None:
    write_project_workspace_version_snapshot(
        project,
        _sorted_chapters(project),
        _sorted_facts(project),
        "Update project workspace",
    )


def _display_name_for_user(user: User | None) -> str | None:
    if not user:
        return None
    nickname = str(user.nickname or "").strip()
    if nickname:
        return nickname
    email = str(user.email or "").strip()
    if email and "@" in email:
        return email.split("@", 1)[0]
    return email or None


def _attach_project_access_payload(project: TextProject, user: User) -> None:
    role = PROJECT_ROLE_ADMIN if user.is_admin else None
    if not role and project.user_id == user.id:
        role = PROJECT_ROLE_OWNER
    if not role:
        for member in project.__dict__.get("members") or []:
            if member.user_id == user.id:
                role = member.role
                break
    if not role and project.visibility == "public":
        role = PROJECT_ROLE_VIEWER
    if role:
        project.current_user_role = role
        project.current_user_permissions = project_permissions_for_role(role)


async def _ensure_default_chapter(project: TextProject, db: AsyncSession) -> ProjectChapter:
    chapters = _sorted_chapters(project)
    if chapters:
        return chapters[0]

    chapter = ProjectChapter(
        project_id=project.id,
        title="Main Draft",
        content="",
        status="draft",
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


def _normalize_operation_prompts(raw: dict[str, str] | None) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    prompts: dict[str, str] = {}
    for key, value in raw.items():
        normalized_key = str(key or "").strip().upper()
        prompt = str(value or "").strip()
        if normalized_key in OPERATION_PROMPT_KEYS and prompt:
            prompts[normalized_key] = prompt
    return prompts


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
    sync_targets = ["memory"] if normalized_source == "chapter" else []
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
        "sync_targets": sync_targets,
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
            "sync_targets": sync_targets,
            "extra": extra or {},
        },
        message=f"Recorded {normalized_source} {normalized_action} sync event",
    )


def _project_auto_memory_sync_enabled(project: TextProject) -> bool:
    component_models = getattr(project, "component_models", None)
    if not isinstance(component_models, dict):
        return True
    raw = str(component_models.get(MEMORY_AUTO_SYNC_COMPONENT_KEY) or "").strip().lower()
    return raw != MEMORY_AUTO_SYNC_DISABLED


def _project_has_memory_material(project: TextProject) -> bool:
    return any(chapter_has_memory_material(chapter) for chapter in _sorted_chapters(project))


async def _start_chapter_memory_refresh(
    project_id: str,
    user_id: str,
    trigger_action: str,
    trigger_entity_id: str | None = None,
    *,
    respect_auto_sync_setting: bool = True,
    require_ready: bool = False,
):
    from app.routers.memory import (
        MemoryBuildRequest,
        _build_memory_task_idempotency_key,
        _run_memory_build_task,
        _start_project_task,
    )

    async with async_session() as schedule_db:
        result = await schedule_db.execute(
            select(TextProject)
            .where(TextProject.id == project_id)
            .options(selectinload(TextProject.chapters))
        )
        project = result.scalar_one_or_none()
        if not project:
            if require_ready:
                raise RuntimeError("Project not found")
            return None
        if respect_auto_sync_setting and not _project_auto_memory_sync_enabled(project):
            return None
        normalized_action = str(trigger_action or "").strip().lower() or "update"
        if normalized_action in {"update", "delete"}:
            if require_ready:
                raise RuntimeError(
                    "Incremental memory sync only supports newly added chapters. "
                    "Use rebuild mode after chapter updates or deletes."
                )
            return None
        if not project.memory_id:
            if require_ready:
                raise RuntimeError("Memory not built. Use rebuild mode before incremental sync.")
            return None

        build_text = "\n\n".join(
            chapter_memory_text(chapter)
            for chapter in _sorted_chapters(project)
            if chapter_has_memory_material(chapter)
        ).strip()
        if not build_text:
            if require_ready:
                raise RuntimeError("No chapter text available for memory sync.")
            return None

        body = MemoryBuildRequest(text=build_text, build_mode="incremental")
        idempotency_key = _build_memory_task_idempotency_key(project_id, body)

    return _start_project_task(
        task_type="memory_build",
        project_id=project_id,
        user_id=user_id,
        metadata={
            "build_mode": "incremental",
            "idempotency_key": idempotency_key,
            "trigger_source_kind": "chapter",
            "trigger_action": normalized_action,
            "trigger_entity_id": str(trigger_entity_id or "").strip() or None,
            "auto_created": True,
        },
        worker=lambda task_id: _run_memory_build_task(
            task_id,
            project_id=project_id,
            text=build_text,
            chapter_ids=None,
            ontology=None,
            build_mode="incremental",
        ),
    )


async def _schedule_chapter_memory_refresh(
    project_id: str,
    user_id: str,
    trigger_action: str,
    trigger_entity_id: str | None = None,
) -> None:
    await _start_chapter_memory_refresh(
        project_id,
        user_id,
        trigger_action,
        trigger_entity_id,
    )


def _trim_text(value: str | None, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)] + "..."


def _build_search_snippet(value: Any, keyword: str, limit: int = 160) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    match_index = lowered.find(keyword.lower())
    if match_index < 0:
        return _trim_text(text, limit)
    half = max(20, limit // 2)
    start = max(0, match_index - half)
    end = min(len(text), match_index + len(keyword) + half)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(text):
        snippet = f"{snippet}..."
    return snippet


def _first_matching_field(fields: list[tuple[str, Any]], keyword: str) -> tuple[str, str] | None:
    normalized = keyword.lower()
    for name, value in fields:
        text = str(value or "")
        if normalized in text.lower():
            return name, _build_search_snippet(text, keyword)
    return None



@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    result = await db.execute(
        accessible_projects_query(user)
        .options(selectinload(TextProject.chapters), selectinload(TextProject.members))
        .order_by(TextProject.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    projects = result.scalars().all()
    for project in projects:
        _attach_project_access_payload(project, user)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get("/public", response_model=list[ProjectPublicResponse])
async def list_public_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, min_length=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    query = (
        select(TextProject)
        .where(TextProject.visibility == PROJECT_VISIBILITY_PUBLIC)
        .options(selectinload(TextProject.members), selectinload(TextProject.user))
    )
    keyword = str(q or "").strip()
    if keyword:
        pattern = f"%{keyword}%"
        query = query.where(or_(TextProject.title.ilike(pattern), TextProject.description.ilike(pattern)))
    result = await db.execute(
        query
        .order_by(TextProject.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    projects = result.scalars().all()
    for project in projects:
        _attach_project_access_payload(project, user)
        project.author_nickname = _display_name_for_user(project.__dict__.get("user"))
    return [ProjectPublicResponse.model_validate(p) for p in projects]


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
        visibility=body.visibility,
        component_models=body.component_models,
        operation_prompts=_normalize_operation_prompts(body.operation_prompts),
        creative_state=body.creative_state,
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=PROJECT_ROLE_OWNER))
    default_chapter = await _ensure_default_chapter(project, db)
    await db.refresh(project)
    await db.refresh(project, attribute_names=["chapters"])
    author_name = (user.nickname or user.email.split("@", 1)[0]).strip()
    initialize_project_git_repo(project.id, author_name=author_name, author_email=user.email)
    write_project_workspace_snapshot(project, [default_chapter], [])
    seed_control_docs(project.id, project)
    stage_project_git_paths(project.id)
    commit_project_git(project.id, "Initialize project workspace")
    push_project_git_branch(project.id, "origin", "main")
    project.current_user_role = PROJECT_ROLE_OWNER
    project.current_user_permissions = project_permissions_for_role(PROJECT_ROLE_OWNER)
    return ProjectResponse.model_validate(project)


def _member_response(member: ProjectMember) -> ProjectMemberResponse:
    user = member.__dict__.get("user")
    return ProjectMemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        email=user.email if user else None,
        role=member.role,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse])
async def list_project_members(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .options(selectinload(ProjectMember.user))
        .order_by(ProjectMember.created_at.asc())
    )
    return [_member_response(member) for member in result.scalars().all()]


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_project_member(
    project_id: str,
    body: ProjectMemberCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    role = validate_project_member_role(body.role)
    user_result = await db.execute(select(User).where(User.email == body.email.strip()))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == target_user.id,
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project member already exists")

    member = ProjectMember(project_id=project_id, user_id=target_user.id, role=role)
    db.add(member)
    await db.flush()
    return ProjectMemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        email=target_user.email,
        role=member.role,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.put("/{project_id}/members/{member_id}", response_model=ProjectMemberResponse)
async def update_project_member(
    project_id: str,
    member_id: str,
    body: ProjectMemberUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id, ProjectMember.id == member_id)
        .options(selectinload(ProjectMember.user))
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project member not found")
    if member.role == PROJECT_ROLE_OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project owner role cannot be changed here")
    member.role = validate_project_member_role(body.role)
    await db.flush()
    return _member_response(member)


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_member(
    project_id: str,
    member_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    result = await db.execute(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.id == member_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project member not found")
    if member.role == PROJECT_ROLE_OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project owner member cannot be deleted here")
    await db.delete(member)
    return None


@router.put("/{project_id}/visibility", response_model=ProjectResponse)
async def update_project_visibility(
    project_id: str,
    body: ProjectVisibilityUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    project.visibility = validate_project_visibility(body.visibility)
    await db.flush()
    await db.refresh(project)
    await db.refresh(project, attribute_names=["chapters"])
    _write_project_workspace(project)
    project.current_user_role = PROJECT_ROLE_ADMIN if user.is_admin else PROJECT_ROLE_OWNER
    project.current_user_permissions = project_permissions_for_role(project.current_user_role)
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}/search", response_model=list[ProjectSearchResult])
async def search_project_content(
    project_id: str,
    q: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    keyword = q.strip()
    if not keyword:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Search query is required")

    project = await _get_project_for_user(project_id, user, db)
    results: list[ProjectSearchResult] = []

    for chapter in _sorted_chapters(project):
        match = _first_matching_field(
            [("title", chapter.title), ("content", chapter.content)],
            keyword,
        )
        if match:
            field, snippet = match
            results.append(
                ProjectSearchResult(
                    item_type="chapter",
                    item_id=chapter.id,
                    title=chapter.title,
                    matched_field=field,
                    snippet=snippet,
                    order_index=chapter.order_index,
                )
            )

    return results


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_EDIT)
    if body.title is not None:
        project.title = body.title
    if body.description is not None:
        project.description = body.description
    if body.component_models is not None:
        project.component_models = body.component_models
    if body.operation_prompts is not None:
        project.operation_prompts = _normalize_operation_prompts(body.operation_prompts)
    if body.creative_state is not None:
        project.creative_state = body.creative_state

    await db.flush()
    await db.refresh(project)
    await db.refresh(project, attribute_names=["chapters"])
    _write_project_workspace(project)
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_DELETE)
    delete_project_git_storage(project_id)
    await db.delete(project)
    return None


@router.get("/{project_id}/chapters", response_model=list[ProjectChapterResponse])
async def list_project_chapters(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db)
    return [ProjectChapterResponse.model_validate(chapter) for chapter in _sorted_chapters(project)]
@router.post("/{project_id}/chapters", response_model=ProjectChapterResponse, status_code=status.HTTP_201_CREATED)
async def create_project_chapter(
    project_id: str,
    body: ProjectChapterCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_EDIT)

    chapters = _sorted_chapters(project)
    next_index = len(chapters) if body.order_index is None else min(max(body.order_index, 0), len(chapters))

    for chapter in chapters:
        if chapter.order_index >= next_index:
            chapter.order_index += 1

    chapter = ProjectChapter(
        project_id=project.id,
        title=(body.title or "Main Draft").strip() or "Main Draft",
        content=body.content or "",
        status=body.status,
        blueprint=body.blueprint,
        plan=body.plan,
        summary=body.summary,
        continuity_notes=body.continuity_notes,
        order_index=next_index,
    )
    db.add(chapter)
    await db.flush()

    await db.refresh(project, attribute_names=["chapters"])
    await _realign_chapter_orders(project, db)
    await db.refresh(project, attribute_names=["chapters"])
    _write_project_workspace(project)
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="chapter",
        action="create",
        entity_id=chapter.id,
        extra={"chapter_ids": [chapter.id]},
    )
    if project.memory_id and project.ontology_schema and _project_has_memory_material(project) and _project_auto_memory_sync_enabled(project):
        background_tasks.add_task(_schedule_chapter_memory_refresh, project.id, user.id, "create", chapter.id)
    return ProjectChapterResponse.model_validate(chapter)


@router.put("/{project_id}/chapters/{chapter_id}", response_model=ProjectChapterResponse)
async def update_project_chapter(
    project_id: str,
    chapter_id: str,
    body: ProjectChapterUpdate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_EDIT)

    target = next((chapter for chapter in _sorted_chapters(project) if chapter.id == chapter_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")

    if body.title is not None:
        target.title = body.title.strip() or target.title
    if body.content is not None:
        target.content = body.content
    if body.status is not None:
        target.status = body.status
    if body.blueprint is not None:
        target.blueprint = body.blueprint
    if body.plan is not None:
        target.plan = body.plan
    if body.summary is not None:
        target.summary = body.summary
    if body.continuity_notes is not None:
        target.continuity_notes = body.continuity_notes

    if body.order_index is not None:
        chapters = _sorted_chapters(project)
        chapters_without_target = [chapter for chapter in chapters if chapter.id != chapter_id]
        new_index = min(max(body.order_index, 0), len(chapters_without_target))
        reordered = chapters_without_target[:new_index] + [target] + chapters_without_target[new_index:]
        for idx, chapter in enumerate(reordered):
            chapter.order_index = idx

    await db.flush()
    await db.refresh(project, attribute_names=["chapters"])
    _write_project_workspace(project)
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
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_EDIT)

    chapters = _sorted_chapters(project)

    target = next((chapter for chapter in chapters if chapter.id == chapter_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")

    await db.delete(target)
    await db.flush()
    await db.refresh(project, attribute_names=["chapters"])
    await _realign_chapter_orders(project, db)
    await db.refresh(project, attribute_names=["chapters"])
    delete_project_chapter_document(project.id, target.id)
    _write_project_workspace(project)
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
    project = await _get_project_for_user(project_id, user, db, PROJECT_PERMISSION_EDIT)

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
    _write_project_workspace(project)
    _record_project_sync_task(
        project_id=project.id,
        user_id=user.id,
        source_kind="chapter",
        action="reorder",
        extra={"chapter_ids": sorted(existing_ids)},
    )

    return [ProjectChapterResponse.model_validate(chapter) for chapter in _sorted_chapters(project)]

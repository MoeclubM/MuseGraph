import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import ProjectChapter, TextOperation, TextProject
from app.models.user import User
from app.schemas.project import (
    OperationRequest,
    OperationResponse,
    ProjectChapterCreate,
    ProjectChapterReorderRequest,
    ProjectChapterResponse,
    ProjectChapterUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.ai import (
    component_key_for_operation,
    resolve_component_model,
    run_operation,
    run_operation_async,
)

router = APIRouter()


async def _get_project_for_user(project_id: str, user: User, db: AsyncSession) -> TextProject:
    result = await db.execute(
        select(TextProject)
        .where(TextProject.id == project_id)
        .options(selectinload(TextProject.chapters))
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


def _normalize_chapter_ids(chapter_ids: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in chapter_ids or []:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


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

    return [ProjectChapterResponse.model_validate(chapter) for chapter in _sorted_chapters(project)]


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

    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=source_input,
        model=model,
        status="PENDING",
        metadata_={"source_chapter_ids": source_chapter_ids} if source_chapter_ids else None,
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

    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=source_input,
        model=model,
        status="PENDING",
        metadata_={"source_chapter_ids": source_chapter_ids} if source_chapter_ids else None,
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

    # Store original file in MinIO for audit
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
    use_model = resolve_component_model(
        project,
        component_key_for_operation(op_type),
        model,
    )
    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=source_input,
        model=use_model,
        status="PENDING",
        metadata_={"source_chapter_ids": source_chapter_ids} if source_chapter_ids else None,
    )
    db.add(operation)
    await db.flush()

    operation = await run_operation(
        operation.id, project, user, op_type, source_input, use_model, db
    )
    return OperationResponse.model_validate(operation)

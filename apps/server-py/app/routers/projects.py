import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import TextOperation, TextProject
from app.models.user import User
from app.schemas.project import (
    OperationRequest,
    OperationResponse,
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
        content=body.content,
        simulation_requirement=body.simulation_requirement,
        component_models=body.component_models,
    )
    db.add(project)
    await db.flush()
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id and user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return ProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if body.title is not None:
        project.title = body.title
    if body.description is not None:
        project.description = body.description
    if body.content is not None:
        project.content = body.content
    if body.simulation_requirement is not None:
        project.simulation_requirement = body.simulation_requirement
    if body.component_models is not None:
        project.component_models = body.component_models
    if body.oasis_analysis is not None:
        project.oasis_analysis = body.oasis_analysis
    await db.flush()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id and user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    await db.delete(project)
    return None


@router.post("/{project_id}/operation", response_model=OperationResponse)
async def create_operation(
    project_id: str,
    body: OperationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    op_type = (body.type or "").upper()
    if op_type != "CREATE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CREATE supports direct text input. Use document upload for other operation types.",
        )
    if not (body.input or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CREATE requires basic input information.",
        )

    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    model = resolve_component_model(
        project,
        component_key_for_operation(op_type),
        body.model,
    )
    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=body.input,
        model=model,
        status="PENDING",
    )
    db.add(operation)
    await db.flush()

    # Run synchronously within the request
    operation = await run_operation(
        operation.id, project, user, op_type, body.input, model, db
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
    if op_type != "CREATE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CREATE supports direct text input. Use document upload for other operation types.",
        )
    if not (body.input or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CREATE requires basic input information.",
        )

    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    model = resolve_component_model(
        project,
        component_key_for_operation(op_type),
        body.model,
    )
    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=body.input,
        model=model,
        status="PENDING",
    )
    db.add(operation)
    await db.flush()

    # Launch async background task
    asyncio.create_task(
        run_operation_async(
            operation.id, project_id, user.id, op_type, body.input, model
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

    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project or (project.user_id != user.id and user.role != "ADMIN"):
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
    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id and user.role != "ADMIN":
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

    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

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

    use_model = resolve_component_model(
        project,
        component_key_for_operation(op_type),
        model,
    )
    operation = TextOperation(
        project_id=project_id,
        type=op_type,
        input=input_text,
        model=use_model,
        status="PENDING",
    )
    db.add(operation)
    await db.flush()

    operation = await run_operation(
        operation.id, project, user, op_type, input_text, use_model, db
    )
    return OperationResponse.model_validate(operation)

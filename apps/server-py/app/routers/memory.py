from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.runtime import AgentRun, ProjectRevision
from app.models.user import User
from app.schemas.runtime import (
    AgentFinish,
    AgentRunResponse,
    ChangeSet,
    KnowledgeOperation,
    SelfReview,
    ValidationResult,
)
from app.services.agent_workspace import apply_knowledge_operations
from app.services.memory_client import list_knowledge_records, recall_knowledge
from app.services.memory_config import ensure_project_memory_instance
from app.services.project_access import (
    PROJECT_PERMISSION_EDIT,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)

router = APIRouter()


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


class KnowledgeChangeRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    operations: list[KnowledgeOperation] = Field(min_length=1)


async def _active_revision(project_id: str, revision_id: str, db: AsyncSession) -> ProjectRevision:
    result = await db.execute(
        select(ProjectRevision).where(
            ProjectRevision.id == revision_id,
            ProjectRevision.project_id == project_id,
        )
    )
    revision = result.scalar_one_or_none()
    if revision is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active revision not found")
    return revision


@router.get("")
async def list_records(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    revision = await _active_revision(project_id, project.active_revision_id, db)
    await ensure_project_memory_instance(project, db)
    return {
        "revision_id": revision.id,
        "dataset_name": revision.knowledge_dataset,
        "records": await list_knowledge_records(project_id, revision.knowledge_dataset),
    }


@router.post("/search")
async def search_records(
    project_id: str,
    body: KnowledgeSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    revision = await _active_revision(project_id, project.active_revision_id, db)
    await ensure_project_memory_instance(project, db)
    records = await list_knowledge_records(project_id, revision.knowledge_dataset)
    if records:
        await ensure_project_memory_instance(project, db, require_models=True)
    results = (
        await recall_knowledge(
            project_id,
            revision.knowledge_dataset,
            body.query,
            top_k=body.top_k,
        )
        if records
        else []
    )
    return {"revision_id": revision.id, "results": results}


@router.post("/changes", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
async def propose_knowledge_changes(
    project_id: str,
    body: KnowledgeChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    revision = await _active_revision(project_id, project.active_revision_id, db)
    await ensure_project_memory_instance(project, db, require_models=True)
    records = await list_knowledge_records(project_id, revision.knowledge_dataset)
    validated_records = apply_knowledge_operations(records, body.operations, "candidate")
    change_set = ChangeSet(
        knowledge=body.operations,
        validation=ValidationResult(
            passed=True,
            checks=[
                {
                    "name": "knowledge_schema",
                    "passed": True,
                    "detail": {"result_count": len(validated_records)},
                }
            ],
        ),
        self_review=SelfReview(
            passed=True,
            summary="Manual structured knowledge changes validated.",
            issues=[],
        ),
    )
    finish = AgentFinish(
        summary=body.instruction,
        changed_files=[],
        knowledge_operations=len(body.operations),
        used_knowledge_ids=[],
        unresolved_issues=[],
    )
    run = AgentRun(
        project_id=project_id,
        user_id=user.id,
        base_revision_id=revision.id,
        mode="write",
        status="awaiting_review",
        instruction=body.instruction,
        target_refs=[],
        skill_snapshot={"slug": "manual-knowledge", "source": "project"},
        change_set=change_set.model_dump(mode="json"),
        final_output=finish.model_dump(mode="json"),
        validation=change_set.validation.model_dump(mode="json"),
        self_review=change_set.self_review.model_dump(mode="json"),
    )
    db.add(run)
    await db.flush()
    return AgentRunResponse.model_validate(run)


@router.get("/visualization")
async def visualize_records(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    revision = await _active_revision(project_id, project.active_revision_id, db)
    await ensure_project_memory_instance(project, db)
    records = await list_knowledge_records(project_id, revision.knowledge_dataset)
    nodes = [
        {
            "id": record["id"],
            "label": record["title"],
            "type": record["kind"],
            "content": record["content"],
        }
        for record in records
        if record["kind"] != "relation"
    ]
    edges = [
        {
            "id": record["id"],
            "source": record["source_id"],
            "target": record["target_id"],
            "label": record["predicate"],
        }
        for record in records
        if record["kind"] == "relation"
    ]
    return {"revision_id": revision.id, "nodes": nodes, "edges": edges}

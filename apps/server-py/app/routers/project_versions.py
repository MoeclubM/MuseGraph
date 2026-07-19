from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from pydantic import TypeAdapter
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
    KnowledgeDelete,
    KnowledgeRecord,
    KnowledgeUpsert,
    ProjectRevisionResponse,
    SelfReview,
    ValidationResult,
)
from app.services.agent_workspace import (
    collect_file_changes,
    create_run_workspace,
    run_workspace_root,
)
from app.services.agent.configuration import resolve_project_agent
from app.services.memory_client import list_knowledge_records
from app.services.project_access import (
    PROJECT_PERMISSION_EDIT,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)
from app.services.project_git import materialize_project_commit

router = APIRouter()
knowledge_record_adapter = TypeAdapter(KnowledgeRecord)


class RestoreRevisionRequest(BaseModel):
    revision_id: str


@router.get("", response_model=list[ProjectRevisionResponse])
async def list_versions(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    result = await db.execute(
        select(ProjectRevision)
        .where(ProjectRevision.project_id == project_id)
        .order_by(ProjectRevision.created_at.desc())
    )
    return [ProjectRevisionResponse.model_validate(item) for item in result.scalars()]


@router.post("/restore", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
async def propose_version_restore(
    project_id: str,
    body: RestoreRevisionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    target_result = await db.execute(
        select(ProjectRevision).where(
            ProjectRevision.id == body.revision_id,
            ProjectRevision.project_id == project_id,
        )
    )
    target = target_result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project revision not found")
    current = (
        await db.execute(
            select(ProjectRevision).where(ProjectRevision.id == project.active_revision_id)
        )
    ).scalar_one()
    project_agent, agent_snapshot = await resolve_project_agent(
        db,
        project=project,
        mode="write",
        requested_agent_id=None,
        require_model=False,
    )
    run = AgentRun(
        project_id=project_id,
        user_id=user.id,
        base_revision_id=current.id,
        agent_id=project_agent.id,
        mode="write",
        status="awaiting_review",
        instruction=f"Restore project revision {target.id}",
        target_refs=[],
        agent_snapshot=agent_snapshot.model_dump(mode="json"),
        skill_snapshot={"slug": "version-restore", "source": "project"},
        change_set={},
    )
    db.add(run)
    await db.flush()
    create_run_workspace(project_id, run.id)
    workspace = run_workspace_root(run.id)
    for path in list(workspace.iterdir()):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    materialize_project_commit(project_id, target.git_commit, workspace)
    file_changes = collect_file_changes(project_id, run.id)
    current_records = {
        record["id"]: record
        for record in await list_knowledge_records(project_id, current.knowledge_dataset)
    }
    target_records = {
        record["id"]: record
        for record in await list_knowledge_records(project_id, target.knowledge_dataset)
    }
    operations = [
        KnowledgeDelete(record_id=record_id)
        for record_id in sorted(set(current_records) - set(target_records))
    ]
    operations.extend(
        KnowledgeUpsert(record=knowledge_record_adapter.validate_python(record))
        for record_id, record in sorted(target_records.items())
        if current_records.get(record_id) != record
    )
    validation = ValidationResult(
        passed=True,
        checks=[{"name": "revision_snapshot", "passed": True, "detail": {"target": target.id}}],
    )
    self_review = SelfReview(
        passed=True,
        summary="Selected Git and Cognee revision snapshots are ready for review.",
        issues=[],
    )
    change_set = ChangeSet(
        files=file_changes,
        knowledge=operations,
        validation=validation,
        self_review=self_review,
    )
    finish = AgentFinish(
        summary=f"Restore revision {target.id}",
        changed_files=[item.path for item in file_changes],
        knowledge_operations=len(operations),
        used_knowledge_ids=[],
        unresolved_issues=[],
    )
    run.change_set = change_set.model_dump(mode="json")
    run.validation = validation.model_dump(mode="json")
    run.self_review = self_review.model_dump(mode="json")
    run.final_output = finish.model_dump(mode="json")
    await db.flush()
    await db.refresh(run)
    return AgentRunResponse.model_validate(run)

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.dependencies import get_current_user
from app.models.project import ProjectChapter, TextProject
from app.models.runtime import ReportRuntime, SimulationRuntime
from app.models.user import User
from app.services.ai import DEFAULT_MODEL, call_llm, llm_billing_scope, resolve_component_model
from app.services.oasis import (
    build_oasis_package,
    build_oasis_run_result,
    generate_oasis_report,
    load_oasis_config,
)
from app.services.task_state import TaskStatus, task_manager

router = APIRouter()


class ReportGenerateRequest(BaseModel):
    simulation_id: str
    force_regenerate: bool = False
    chapter_ids: list[str] | None = None


class ReportStatusRequest(BaseModel):
    task_id: str | None = None
    simulation_id: str | None = None


class ReportChatRequest(BaseModel):
    simulation_id: str
    message: str = Field(min_length=1)
    chat_history: list[dict[str, Any]] | None = None


class ReportToolSearchRequest(BaseModel):
    report_id: str | None = None
    simulation_id: str | None = None
    query: str = Field(min_length=1)


class ReportToolStatisticsRequest(BaseModel):
    simulation_id: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ensure_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_provenance(*, source_chapter_ids: list[str], text: str) -> dict[str, Any]:
    return {
        "source_chapter_ids": source_chapter_ids,
        "content_hash": _hash_text(text),
        "generated_at": _now_iso(),
    }


def _inject_provenance(payload: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    payload["source_chapter_ids"] = list(provenance.get("source_chapter_ids") or [])
    payload["content_hash"] = str(provenance.get("content_hash") or "")
    payload["generated_at"] = str(provenance.get("generated_at") or _now_iso())
    payload["provenance"] = {
        "source_chapter_ids": payload["source_chapter_ids"],
        "content_hash": payload["content_hash"],
        "generated_at": payload["generated_at"],
    }
    return payload


def _read_provenance(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    source_chapter_ids = payload.get("source_chapter_ids")
    content_hash = payload.get("content_hash")
    generated_at = payload.get("generated_at")
    if isinstance(payload.get("provenance"), dict):
        nested = payload["provenance"]
        if source_chapter_ids is None:
            source_chapter_ids = nested.get("source_chapter_ids")
        if not content_hash:
            content_hash = nested.get("content_hash")
        if not generated_at:
            generated_at = nested.get("generated_at")

    normalized_ids = _normalize_chapter_ids(source_chapter_ids if isinstance(source_chapter_ids, list) else None)
    hash_value = str(content_hash or "").strip()
    generated = str(generated_at or "").strip() or _now_iso()
    if not hash_value:
        return None
    return {
        "source_chapter_ids": normalized_ids,
        "content_hash": hash_value,
        "generated_at": generated,
    }


async def _resolve_chapters_for_project(
    project: TextProject,
    chapter_ids: list[str] | None,
    db: AsyncSession,
) -> list[ProjectChapter]:
    if chapter_ids:
        result = await db.execute(
            select(ProjectChapter).where(
                ProjectChapter.project_id == project.id,
                ProjectChapter.id.in_(chapter_ids),
            )
        )
        chapters = result.scalars().all()
        chapter_map = {chapter.id: chapter for chapter in chapters}
        missing = [chapter_id for chapter_id in chapter_ids if chapter_id not in chapter_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid chapter_ids for project: {', '.join(missing)}",
            )
        return sorted(chapters, key=lambda c: (c.order_index, c.created_at, c.id))

    existing = getattr(project, "chapters", None)
    if isinstance(existing, list):
        return sorted(existing, key=lambda c: (c.order_index, c.created_at, c.id))

    result = await db.execute(
        select(ProjectChapter).where(ProjectChapter.project_id == project.id)
    )
    chapters = result.scalars().all()
    return sorted(chapters, key=lambda c: (c.order_index, c.created_at, c.id))


async def _resolve_text_for_project(
    project: TextProject,
    *,
    chapter_ids: list[str] | None,
    db: AsyncSession,
) -> tuple[str, dict[str, Any]]:
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
        text = "\n\n".join((chapter.content or "").strip() for chapter in chapters if chapter.content is not None).strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected chapters have no text content",
            )
        return text, _build_provenance(source_chapter_ids=[chapter.id for chapter in chapters], text=text)

    chapters = await _resolve_chapters_for_project(project, None, db)
    chapter_text = "\n\n".join((chapter.content or "").strip() for chapter in chapters if chapter.content is not None).strip()
    text = chapter_text
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no text content",
        )
    return text, _build_provenance(source_chapter_ids=[], text=text)


def _split_markdown_sections(markdown: str | None) -> list[dict[str, Any]]:
    text = (markdown or "").strip()
    if not text:
        return []
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    title = "Overview"
    bucket: list[str] = []
    for line in lines:
        if re.match(r"^#{1,3}\s+", line):
            if bucket:
                sections.append(
                    {
                        "index": len(sections),
                        "title": title,
                        "content": "\n".join(bucket).strip(),
                    }
                )
                bucket = []
            title = re.sub(r"^#{1,3}\s+", "", line).strip() or "Untitled"
        else:
            bucket.append(line)
    if bucket:
        sections.append(
            {
                "index": len(sections),
                "title": title,
                "content": "\n".join(bucket).strip(),
            }
        )
    return sections


async def _get_simulation_for_user(simulation_id: str, user: User, db: AsyncSession) -> SimulationRuntime:
    result = await db.execute(
        select(SimulationRuntime).where(SimulationRuntime.simulation_id == simulation_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found")
    if sim.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return sim


async def _get_report_for_user(report_id: str, user: User, db: AsyncSession) -> ReportRuntime:
    result = await db.execute(select(ReportRuntime).where(ReportRuntime.report_id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    if report.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return report


def _serialize_report(report: ReportRuntime) -> dict[str, Any]:
    payload = _ensure_dict(report.report_payload)
    payload.setdefault("report_id", report.report_id)
    payload.setdefault("simulation_id", report.simulation_id)
    payload.setdefault("status", report.status)
    payload.setdefault("title", report.title or "")
    payload.setdefault("executive_summary", report.executive_summary or "")
    payload.setdefault("markdown", report.markdown_content or "")
    payload.setdefault("generated_at", report.updated_at.isoformat() if report.updated_at else None)
    return payload


async def _run_report_task(task_id: str, report_id: str) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading simulation artifacts...",
    )
    async with async_session() as db:
        try:
            report_result = await db.execute(select(ReportRuntime).where(ReportRuntime.report_id == report_id))
            report = report_result.scalar_one_or_none()
            if not report:
                raise RuntimeError("Report not found")

            sim_result = await db.execute(
                select(SimulationRuntime).where(SimulationRuntime.simulation_id == report.simulation_id)
            )
            sim = sim_result.scalar_one_or_none()
            if not sim:
                raise RuntimeError("Simulation not found")

            project_result = await db.execute(select(TextProject).where(TextProject.id == sim.project_id))
            project = project_result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            task_manager.update_task(task_id, progress=25, message="Preparing report context...")
            analysis = _ensure_dict(project.oasis_analysis)
            oasis_config = await load_oasis_config(db)
            package = _ensure_dict(analysis.get("latest_package"))
            if not package:
                package = build_oasis_package(
                    project_id=project.id,
                    project_title=project.title,
                    requirement=(project.simulation_requirement or "").strip(),
                    ontology=_ensure_dict(project.ontology_schema),
                    analysis=analysis,
                    component_models=project.component_models if isinstance(project.component_models, dict) else None,
                    oasis_config=oasis_config,
                )

            run_state = _ensure_dict(sim.run_state)
            run_result = _ensure_dict(run_state.get("run_result"))
            if not run_result:
                run_result = _ensure_dict(analysis.get("latest_run"))
            if not run_result:
                run_result = build_oasis_run_result(package=package, analysis=analysis)

            model = resolve_component_model(project, "oasis_report")
            task_manager.update_task(task_id, progress=55, message="Generating report...")
            with llm_billing_scope(
                user_id=report.user_id,
                project_id=sim.project_id,
            ):
                generated = await generate_oasis_report(
                    package=package,
                    analysis=analysis,
                    run_result=run_result,
                    requirement=(project.simulation_requirement or "").strip() or None,
                    model=model,
                    oasis_config=oasis_config,
                    db=db,
                )

            markdown = str(generated.get("markdown") or "")
            sections = _split_markdown_sections(markdown)
            report.status = "completed"
            report.title = str(generated.get("title") or "")
            report.executive_summary = str(generated.get("executive_summary") or "")
            report.markdown_content = markdown
            report.sections = sections
            current_provenance = _read_provenance(_ensure_dict(report.report_payload))
            if current_provenance:
                generated = _inject_provenance(_ensure_dict(generated), current_provenance)
                sim.metadata_ = _inject_provenance(_ensure_dict(sim.metadata_), current_provenance)
                sim.run_state = _inject_provenance(_ensure_dict(sim.run_state), current_provenance)
            report.report_payload = generated
            report.agent_log = _ensure_list(report.agent_log) + [
                {"line": "Report generation completed", "created_at": _now_iso()}
            ]
            report.console_log = _ensure_list(report.console_log) + [
                {"line": f"Report {report.report_id} ready", "created_at": _now_iso()}
            ]
            await db.flush()
            await db.commit()
            task_manager.complete_task(
                task_id,
                result={"report_id": report.report_id, "simulation_id": report.simulation_id},
                message="Report generated",
            )
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, str(exc), "Report generation failed")


@router.post("/generate")
async def generate_report(
    body: ReportGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(body.simulation_id, user, db)
    project_result = await db.execute(select(TextProject).where(TextProject.id == sim.project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if not body.force_regenerate:
        existing = await db.execute(
            select(ReportRuntime)
            .where(ReportRuntime.simulation_id == sim.simulation_id)
            .where(ReportRuntime.status == "completed")
            .order_by(desc(ReportRuntime.updated_at))
        )
        completed = existing.scalars().first()
        if completed:
            return {
                "status": "ok",
                "data": {
                    "simulation_id": sim.simulation_id,
                    "report_id": completed.report_id,
                    "already_generated": True,
                },
            }

    task_manager.cleanup_old_tasks(max_age_hours=168)
    text, provenance = await _resolve_text_for_project(
        project=project,
        chapter_ids=body.chapter_ids,
        db=db,
    )

    sim.metadata_ = _inject_provenance(_ensure_dict(sim.metadata_), provenance)
    sim.simulation_config = _inject_provenance(_ensure_dict(sim.simulation_config), provenance)
    sim.run_state = _inject_provenance(_ensure_dict(sim.run_state), provenance)
    await db.flush()

    task = task_manager.create_task(
        "report_generate",
        metadata={
            "simulation_id": sim.simulation_id,
            "project_id": sim.project_id,
            "user_id": user.id,
            **_inject_provenance({}, provenance),
        },
    )
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    report = ReportRuntime(
        report_id=report_id,
        simulation_id=sim.simulation_id,
        project_id=sim.project_id,
        user_id=sim.user_id,
        status="processing",
        title="",
        executive_summary="",
        markdown_content="",
        report_payload=_inject_provenance(
            {
                "report_id": report_id,
                "simulation_id": sim.simulation_id,
                "status": "processing",
                "source_text_preview": text[:2000],
            },
            provenance,
        ),
        sections=[],
        chat_history=[],
        agent_log=[{"line": "Report task queued", "created_at": _now_iso()}],
        console_log=[{"line": f"task_id={task.task_id}", "created_at": _now_iso()}],
    )
    db.add(report)
    await db.flush()
    asyncio.create_task(_run_report_task(task.task_id, report.report_id))
    return {
        "status": "ok",
        "data": {
            "simulation_id": sim.simulation_id,
            "report_id": report.report_id,
            "task_id": task.task_id,
            "message": "Report task started",
        },
    }


@router.post("/generate/status")
async def get_generate_status(
    body: ReportStatusRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.simulation_id:
        sim = await _get_simulation_for_user(body.simulation_id, user, db)
        report_result = await db.execute(
            select(ReportRuntime)
            .where(ReportRuntime.simulation_id == sim.simulation_id)
            .order_by(desc(ReportRuntime.updated_at))
        )
        latest = report_result.scalars().first()
        if latest and latest.status == "completed":
            return {
                "status": "ok",
                "data": {
                    "status": "completed",
                    "simulation_id": sim.simulation_id,
                    "report_id": latest.report_id,
                },
            }
    if not body.task_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="task_id or simulation_id required")
    task = task_manager.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return {"status": "ok", "data": task.to_dict()}


@router.get("/by-simulation/{simulation_id}")
async def get_report_by_simulation(
    simulation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    report_result = await db.execute(
        select(ReportRuntime)
        .where(ReportRuntime.simulation_id == sim.simulation_id)
        .order_by(desc(ReportRuntime.updated_at))
    )
    report = report_result.scalars().first()
    if not report:
        return {"status": "ok", "data": None, "has_report": False}
    return {"status": "ok", "data": _serialize_report(report), "has_report": True}


@router.get("/list")
async def list_reports(
    simulation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ReportRuntime)
    if not user.is_admin:
        stmt = stmt.where(ReportRuntime.user_id == user.id)
    if simulation_id:
        stmt = stmt.where(ReportRuntime.simulation_id == simulation_id)
    stmt = stmt.order_by(desc(ReportRuntime.created_at)).limit(limit)
    reports = (await db.execute(stmt)).scalars().all()
    return {"status": "ok", "data": [_serialize_report(r) for r in reports], "count": len(reports)}


@router.get("/check/{simulation_id}")
async def check_report_status(
    simulation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_simulation_for_user(simulation_id, user, db)
    report_result = await db.execute(
        select(ReportRuntime)
        .where(ReportRuntime.simulation_id == simulation_id)
        .order_by(desc(ReportRuntime.updated_at))
    )
    report = report_result.scalars().first()
    has_report = report is not None
    return {
        "status": "ok",
        "data": {
            "simulation_id": simulation_id,
            "has_report": has_report,
            "report_status": report.status if report else None,
            "report_id": report.report_id if report else None,
            "interview_unlocked": bool(report and report.status == "completed"),
        },
    }


@router.post("/chat")
async def chat_with_report_agent(
    body: ReportChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(body.simulation_id, user, db)
    report_result = await db.execute(
        select(ReportRuntime)
        .where(ReportRuntime.simulation_id == sim.simulation_id)
        .order_by(desc(ReportRuntime.updated_at))
    )
    report = report_result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found for simulation")

    project_result = await db.execute(select(TextProject).where(TextProject.id == sim.project_id))
    project = project_result.scalar_one_or_none()
    model = resolve_component_model(project, "oasis_report") if project else DEFAULT_MODEL
    payload = _ensure_dict(report.report_payload)
    prompt = (
        "You are an analysis assistant for OASIS simulation report.\n"
        f"Report summary: {payload.get('executive_summary', '')}\n"
        f"Key findings: {payload.get('key_findings', [])}\n"
        f"User question: {body.message}"
    )
    try:
        with llm_billing_scope(
            user_id=user.id,
            project_id=sim.project_id,
        ):
            llm_result = await call_llm(model=model, prompt=prompt, db=db)
        answer = str(llm_result.get("content") or "").strip()
    except Exception:
        answer = "No model response available."

    history = _ensure_list(report.chat_history)
    history.append({"role": "user", "content": body.message, "created_at": _now_iso()})
    history.append({"role": "assistant", "content": answer, "created_at": _now_iso()})
    report.chat_history = history[-500:]
    report.agent_log = _ensure_list(report.agent_log) + [{"line": f"Q: {body.message}", "created_at": _now_iso()}]
    await db.flush()
    return {"status": "ok", "data": {"answer": answer, "chat_history": report.chat_history}}


@router.post("/tools/search")
async def report_tools_search(
    body: ReportToolSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report: ReportRuntime | None = None
    if body.report_id:
        report = await _get_report_for_user(body.report_id, user, db)
    elif body.simulation_id:
        sim = await _get_simulation_for_user(body.simulation_id, user, db)
        report_result = await db.execute(
            select(ReportRuntime)
            .where(ReportRuntime.simulation_id == sim.simulation_id)
            .order_by(desc(ReportRuntime.updated_at))
        )
        report = report_result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    query = body.query.lower()
    payload = _ensure_dict(report.report_payload)
    candidates = []
    for key in ("title", "executive_summary"):
        value = str(payload.get(key) or "")
        if query in value.lower():
            candidates.append({"field": key, "content": value})
    for value in _ensure_list(payload.get("key_findings")):
        text = str(value or "")
        if query in text.lower():
            candidates.append({"field": "key_findings", "content": text})
    return {"status": "ok", "data": candidates, "count": len(candidates)}


@router.post("/tools/statistics")
async def report_tools_statistics(
    body: ReportToolStatisticsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(body.simulation_id, user, db)
    posts = _ensure_list(sim.posts)
    comments = _ensure_list(sim.comments)
    actions = _ensure_list(sim.actions)
    run_state = _ensure_dict(sim.run_state)
    metrics = _ensure_dict(_ensure_dict(run_state.get("run_result")).get("metrics"))
    return {
        "status": "ok",
        "data": {
            "simulation_id": sim.simulation_id,
            "post_count": len(posts),
            "comment_count": len(comments),
            "action_count": len(actions),
            "metrics": metrics,
        },
    }


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_report_for_user(report_id, user, db)
    return {"status": "ok", "data": _serialize_report(report)}


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_report_for_user(report_id, user, db)
    content = report.markdown_content or ""
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report.report_id}.md"'},
    )


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_report_for_user(report_id, user, db)
    await db.delete(report)
    return {"status": "ok", "message": f"Report deleted: {report_id}"}


@router.get("/{report_id}/progress")
async def get_report_progress(
    report_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_report_for_user(report_id, user, db)
    status_value = report.status
    progress = 100 if status_value == "completed" else 50 if status_value == "processing" else 0
    return {"status": "ok", "data": {"report_id": report.report_id, "status": status_value, "progress": progress}}


@router.get("/{report_id}/sections")
async def get_report_sections(
    report_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_report_for_user(report_id, user, db)
    sections = _ensure_list(report.sections)
    if not sections and report.markdown_content:
        sections = _split_markdown_sections(report.markdown_content)
        report.sections = sections
        await db.flush()
    return {
        "status": "ok",
        "data": {
            "report_id": report.report_id,
            "sections": sections,
            "count": len(sections),
            "is_complete": report.status == "completed",
        },
    }


@router.get("/{report_id}/section/{section_index}")
async def get_single_section(
    report_id: str,
    section_index: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_report_for_user(report_id, user, db)
    sections = _ensure_list(report.sections)
    if not sections and report.markdown_content:
        sections = _split_markdown_sections(report.markdown_content)
    if section_index < 0 or section_index >= len(sections):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    return {"status": "ok", "data": sections[section_index]}


@router.get("/{report_id}/agent-log")
async def get_agent_log(
    report_id: str,
    from_line: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_report_for_user(report_id, user, db)
    logs = _ensure_list(report.agent_log)
    return {"status": "ok", "data": {"report_id": report.report_id, "logs": logs[from_line:], "from_line": from_line}}


@router.get("/{report_id}/console-log")
async def get_console_log(
    report_id: str,
    from_line: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_report_for_user(report_id, user, db)
    logs = _ensure_list(report.console_log)
    return {"status": "ok", "data": {"report_id": report.report_id, "logs": logs[from_line:], "from_line": from_line}}

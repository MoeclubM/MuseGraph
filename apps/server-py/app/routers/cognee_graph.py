import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.dependencies import get_current_user
from app.models.project import TextProject
from app.models.user import User
from app.schemas.cognee import (
    CogneeAddRequest,
    CogneeOasisAnalyzeRequest,
    CogneeOasisAnalyzeResponse,
    CogneeOasisPrepareRequest,
    CogneeOasisPrepareResponse,
    CogneeOasisReportRequest,
    CogneeOasisReportResponse,
    CogneeOasisRunRequest,
    CogneeOasisRunResponse,
    CogneeTaskInfo,
    CogneeTaskListResponse,
    CogneeTaskStartResponse,
    CogneeTaskStatusResponse,
    CogneeOntologyGenerateRequest,
    CogneeOntologyResponse,
    CogneeSearchRequest,
    CogneeStatusResponse,
    CogneeVisualizationResponse,
)
from app.services.cognee import (
    add_and_cognify,
    delete_dataset,
    get_graph_visualization,
    search_graph,
)
from app.services.ai import resolve_component_model
from app.services.oasis import (
    analyze_and_enrich_oasis,
    build_oasis_package,
    build_oasis_run_result,
    generate_oasis_report,
)
from app.services.ontology import build_graph_input_with_ontology, generate_ontology
from app.services.task_state import TaskRecord, TaskStatus, task_manager

router = APIRouter()


async def _get_project(project_id: str, user: User, db: AsyncSession) -> TextProject:
    result = await db.execute(select(TextProject).where(TextProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id and user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return project


def _require_ontology_and_graph(project: TextProject, action_name: str) -> None:
    if not project.ontology_schema:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ontology not generated. Please complete ontology first before {action_name}.",
        )
    if not project.cognee_dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Graph not built. Please build graph before {action_name}.",
        )


def _resolve_text(body_text: str | None, project: TextProject, error_detail: str) -> str:
    text = (body_text or "").strip() or (project.content or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail,
        )
    return text


def _resolve_requirement(body_requirement: str | None, project: TextProject) -> str | None:
    if body_requirement is None:
        return (project.simulation_requirement or "").strip() or None
    return body_requirement.strip() or None


def _resolve_requirement_input(*, requirement: str | None, provided: bool, project: TextProject) -> str | None:
    if provided:
        return (requirement or "").strip() or None
    return _resolve_requirement(None, project)


def _resolve_analysis_model(project: TextProject, body: CogneeOasisAnalyzeRequest | CogneeOasisPrepareRequest) -> str:
    explicit = (body.analysis_model or body.model or None)
    return resolve_component_model(project, "oasis_analysis", explicit)


def _resolve_simulation_model(project: TextProject, body: CogneeOasisAnalyzeRequest | CogneeOasisPrepareRequest) -> str:
    explicit = (body.simulation_model or body.model or None)
    return resolve_component_model(project, "oasis_simulation_config", explicit)


def _resolve_report_model(project: TextProject, body: CogneeOasisReportRequest) -> str:
    explicit = (body.report_model or body.model or None)
    return resolve_component_model(project, "oasis_report", explicit)


def _get_project_analysis(project: TextProject) -> dict[str, Any] | None:
    return project.oasis_analysis if isinstance(project.oasis_analysis, dict) else None


def _store_analysis_payload(project: TextProject, **fields: Any) -> dict[str, Any]:
    base = dict(project.oasis_analysis or {})
    for key, value in fields.items():
        base[key] = value
    project.oasis_analysis = base
    return base


def _task_to_schema(task: TaskRecord) -> CogneeTaskInfo:
    return CogneeTaskInfo.model_validate(task.to_dict())


async def _generate_and_store_oasis_analysis(
    *,
    project: TextProject,
    project_id: str,
    text: str,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str,
    simulation_model: str,
    db: AsyncSession,
) -> tuple[dict, dict]:
    analysis, context = await analyze_and_enrich_oasis(
        project_id=project_id,
        text=text,
        ontology=project.ontology_schema,
        requirement=requirement,
        prompt=prompt,
        analysis_model=analysis_model,
        simulation_model=simulation_model,
        db=db,
    )
    project.oasis_analysis = analysis
    await db.flush()
    return analysis, context


async def _prepare_and_store_oasis_package(
    *,
    project: TextProject,
    project_id: str,
    text: str | None,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str,
    simulation_model: str,
    db: AsyncSession,
) -> dict[str, Any]:
    analysis = _get_project_analysis(project)

    if not analysis:
        source_text = _resolve_text(text, project, "No source text provided for OASIS analysis")
        analysis, _ = await _generate_and_store_oasis_analysis(
            project=project,
            project_id=project_id,
            text=source_text,
            requirement=requirement,
            prompt=prompt,
            analysis_model=analysis_model,
            simulation_model=simulation_model,
            db=db,
        )

    package = build_oasis_package(
        project_id=project.id,
        project_title=project.title,
        requirement=requirement,
        ontology=project.ontology_schema,
        analysis=analysis,
        component_models=project.component_models if isinstance(project.component_models, dict) else None,
    )
    _store_analysis_payload(project, latest_package=package)
    await db.flush()
    return package


async def _run_prepare_task(
    task_id: str,
    *,
    project_id: str,
    text: str | None,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str | None,
    simulation_model: str | None,
    requirement_provided: bool,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading project context...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            _require_ontology_and_graph(project, "OASIS preparation")
            effective_requirement = _resolve_requirement_input(
                requirement=requirement,
                provided=requirement_provided,
                project=project,
            )
            if requirement_provided:
                project.simulation_requirement = effective_requirement
            selected_analysis_model = analysis_model or resolve_component_model(project, "oasis_analysis")
            selected_simulation_model = simulation_model or resolve_component_model(project, "oasis_simulation_config")

            task_manager.update_task(task_id, progress=35, message="Preparing OASIS package...")
            package = await _prepare_and_store_oasis_package(
                project=project,
                project_id=project_id,
                text=text,
                requirement=effective_requirement,
                prompt=prompt,
                analysis_model=selected_analysis_model,
                simulation_model=selected_simulation_model,
                db=db,
            )
            await db.commit()
            task_manager.complete_task(
                task_id,
                {"package": package},
                "OASIS package prepared",
            )
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, str(exc), "Failed to prepare OASIS package")


async def _run_simulation_task(task_id: str, *, project_id: str, package_override: dict[str, Any] | None) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading OASIS package...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")
            _require_ontology_and_graph(project, "OASIS simulation")
            analysis = _get_project_analysis(project)
            package = package_override
            if not isinstance(package, dict):
                package = (analysis or {}).get("latest_package") if isinstance(analysis, dict) else None
            if not isinstance(package, dict):
                raise RuntimeError("No OASIS package available. Run prepare first.")

            task_manager.update_task(task_id, progress=40, message="Running simulation estimation...")
            run_result = build_oasis_run_result(package=package, analysis=analysis)
            _store_analysis_payload(project, latest_run=run_result)
            await db.flush()
            await db.commit()
            task_manager.complete_task(
                task_id,
                {"run_result": run_result},
                "OASIS simulation run completed",
            )
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, str(exc), "Failed to run OASIS simulation")


async def _run_report_task(
    task_id: str,
    *,
    project_id: str,
    report_model: str | None,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading run artifacts...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")
            analysis = _get_project_analysis(project) or {}
            package = analysis.get("latest_package") if isinstance(analysis.get("latest_package"), dict) else None
            run_result = analysis.get("latest_run") if isinstance(analysis.get("latest_run"), dict) else None
            if not package:
                raise RuntimeError("No OASIS package available. Run prepare first.")
            if not run_result:
                run_result = build_oasis_run_result(package=package, analysis=analysis)
                _store_analysis_payload(project, latest_run=run_result)
                await db.flush()

            selected_report_model = report_model or resolve_component_model(project, "oasis_report")
            task_manager.update_task(task_id, progress=45, message="Generating OASIS report...")
            report = await generate_oasis_report(
                package=package,
                analysis=analysis,
                run_result=run_result,
                requirement=(project.simulation_requirement or "").strip() or None,
                model=selected_report_model,
                db=db,
            )
            _store_analysis_payload(project, latest_report=report)
            await db.flush()
            await db.commit()
            task_manager.complete_task(
                task_id,
                {"report": report},
                "OASIS report generated",
            )
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, str(exc), "Failed to generate OASIS report")


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_to_graph(
    project_id: str,
    body: CogneeAddRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    try:
        if body.ontology:
            project.ontology_schema = body.ontology
        if not project.ontology_schema:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ontology not generated. Please generate ontology first.",
            )
        graph_input = build_graph_input_with_ontology(body.text, project.ontology_schema)
        dataset_name = await add_and_cognify(project_id, graph_input)
        project.cognee_dataset_id = dataset_name
        await db.flush()
        return {"status": "ok", "dataset_id": dataset_name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/ontology/generate", response_model=CogneeOntologyResponse)
async def generate_project_ontology(
    project_id: str,
    body: CogneeOntologyGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    text = (body.text or "").strip() or (project.content or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No source text provided for ontology generation",
        )
    try:
        model = resolve_component_model(project, "ontology_generation", body.model)
        ontology = await generate_ontology(
            text=text,
            db=db,
            requirement=body.requirement,
            model=model,
        )
        project.ontology_schema = ontology
        if body.requirement is not None:
            project.simulation_requirement = body.requirement.strip() or None
        await db.flush()
        return CogneeOntologyResponse(status="ok", ontology=ontology)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/oasis/analyze", response_model=CogneeOasisAnalyzeResponse)
async def analyze_with_oasis(
    project_id: str,
    body: CogneeOasisAnalyzeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS analysis")
    text = _resolve_text(body.text, project, "No source text provided for OASIS analysis")
    requirement_provided = "requirement" in body.model_fields_set
    requirement = _resolve_requirement_input(
        requirement=body.requirement,
        provided=requirement_provided,
        project=project,
    )
    analysis_model = _resolve_analysis_model(project, body)
    simulation_model = _resolve_simulation_model(project, body)
    if requirement_provided:
        project.simulation_requirement = requirement

    try:
        analysis, context = await _generate_and_store_oasis_analysis(
            project=project,
            project_id=project_id,
            text=text,
            requirement=requirement,
            prompt=body.prompt,
            analysis_model=analysis_model,
            simulation_model=simulation_model,
            db=db,
        )
        return CogneeOasisAnalyzeResponse(status="ok", analysis=analysis, context=context)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/oasis/prepare", response_model=CogneeOasisPrepareResponse)
async def prepare_oasis_package(
    project_id: str,
    body: CogneeOasisPrepareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS preparation")
    requirement_provided = "requirement" in body.model_fields_set
    requirement = _resolve_requirement_input(
        requirement=body.requirement,
        provided=requirement_provided,
        project=project,
    )
    analysis_model = _resolve_analysis_model(project, body)
    simulation_model = _resolve_simulation_model(project, body)
    if requirement_provided:
        project.simulation_requirement = requirement
    try:
        package = await _prepare_and_store_oasis_package(
            project=project,
            project_id=project_id,
            text=body.text,
            requirement=requirement,
            prompt=body.prompt,
            analysis_model=analysis_model,
            simulation_model=simulation_model,
            db=db,
        )
        return CogneeOasisPrepareResponse(status="ok", package=package)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/oasis/prepare/task", response_model=CogneeTaskStartResponse)
async def prepare_oasis_package_task(
    project_id: str,
    body: CogneeOasisPrepareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS preparation")
    task_manager.cleanup_old_tasks(max_age_hours=24)
    task = task_manager.create_task(
        "oasis_prepare",
        {
            "project_id": project_id,
            "user_id": user.id,
        },
    )
    asyncio.create_task(
        _run_prepare_task(
            task.task_id,
            project_id=project_id,
            text=body.text,
            requirement=body.requirement,
            prompt=body.prompt,
            analysis_model=_resolve_analysis_model(project, body),
            simulation_model=_resolve_simulation_model(project, body),
            requirement_provided="requirement" in body.model_fields_set,
        )
    )
    return CogneeTaskStartResponse(status="accepted", task=_task_to_schema(task))


@router.post("/oasis/run", response_model=CogneeOasisRunResponse)
async def run_oasis_simulation(
    project_id: str,
    body: CogneeOasisRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS simulation")
    analysis = _get_project_analysis(project) or {}
    package = body.package if isinstance(body.package, dict) else analysis.get("latest_package")
    if not isinstance(package, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No OASIS package available. Prepare package first.")
    run_result = build_oasis_run_result(package=package, analysis=analysis)
    _store_analysis_payload(project, latest_run=run_result)
    await db.flush()
    return CogneeOasisRunResponse(status="ok", run_result=run_result)


@router.post("/oasis/run/task", response_model=CogneeTaskStartResponse)
async def run_oasis_simulation_task(
    project_id: str,
    body: CogneeOasisRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS simulation")
    task_manager.cleanup_old_tasks(max_age_hours=24)
    task = task_manager.create_task(
        "oasis_run",
        {
            "project_id": project_id,
            "user_id": user.id,
        },
    )
    package_override = body.package if isinstance(body.package, dict) else None
    asyncio.create_task(
        _run_simulation_task(
            task.task_id,
            project_id=project_id,
            package_override=package_override,
        )
    )
    return CogneeTaskStartResponse(status="accepted", task=_task_to_schema(task))


@router.post("/oasis/report", response_model=CogneeOasisReportResponse)
async def generate_oasis_report_sync(
    project_id: str,
    body: CogneeOasisReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS report generation")
    analysis = _get_project_analysis(project) or {}
    package = analysis.get("latest_package") if isinstance(analysis.get("latest_package"), dict) else None
    if not package:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No OASIS package available. Prepare package first.")
    run_result = analysis.get("latest_run") if isinstance(analysis.get("latest_run"), dict) else None
    if not run_result:
        run_result = build_oasis_run_result(package=package, analysis=analysis)
        _store_analysis_payload(project, latest_run=run_result)
    report = await generate_oasis_report(
        package=package,
        analysis=analysis,
        run_result=run_result,
        requirement=(project.simulation_requirement or "").strip() or None,
        model=_resolve_report_model(project, body),
        db=db,
    )
    _store_analysis_payload(project, latest_report=report)
    await db.flush()
    return CogneeOasisReportResponse(status="ok", report=report)


@router.post("/oasis/report/task", response_model=CogneeTaskStartResponse)
async def generate_oasis_report_task(
    project_id: str,
    body: CogneeOasisReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS report generation")
    task_manager.cleanup_old_tasks(max_age_hours=24)
    task = task_manager.create_task(
        "oasis_report",
        {
            "project_id": project_id,
            "user_id": user.id,
        },
    )
    asyncio.create_task(
        _run_report_task(
            task.task_id,
            project_id=project_id,
            report_model=_resolve_report_model(project, body),
        )
    )
    return CogneeTaskStartResponse(status="accepted", task=_task_to_schema(task))


@router.get("/oasis/tasks/{task_id}", response_model=CogneeTaskStatusResponse)
async def get_oasis_task_status(
    project_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if str((task.metadata or {}).get("project_id") or "") != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return CogneeTaskStatusResponse(status="ok", task=_task_to_schema(task))


@router.get("/oasis/tasks", response_model=CogneeTaskListResponse)
async def list_oasis_tasks(
    project_id: str,
    task_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    tasks = task_manager.list_tasks(task_type=task_type, project_id=project_id, limit=limit)
    return CogneeTaskListResponse(status="ok", tasks=[_task_to_schema(task) for task in tasks])


@router.get("", response_model=CogneeStatusResponse)
async def get_graph_status(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    if project.cognee_dataset_id:
        return CogneeStatusResponse(
            dataset_id=project.cognee_dataset_id,
            status="ready",
            ontology_status="ready" if project.ontology_schema else "empty",
            oasis_status="ready" if project.oasis_analysis else "empty",
        )
    return CogneeStatusResponse(
        status="empty",
        ontology_status="ready" if project.ontology_schema else "empty",
        oasis_status="ready" if project.oasis_analysis else "empty",
    )


@router.post("/search")
async def search(
    project_id: str,
    body: CogneeSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    if not project.cognee_dataset_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No graph data for this project")
    results = await search_graph(project_id, body.query, body.search_type, body.top_k)
    return {"results": results}


@router.get("/visualization", response_model=CogneeVisualizationResponse)
async def visualization(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    data = await get_graph_visualization(project_id)
    return CogneeVisualizationResponse(nodes=data["nodes"], edges=data["edges"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_graph(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    if project.cognee_dataset_id:
        try:
            await delete_dataset(project_id)
        except Exception:
            pass
        project.cognee_dataset_id = None
        await db.flush()
    return None

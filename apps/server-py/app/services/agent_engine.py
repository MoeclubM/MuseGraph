from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session
from app.models.project import TextProject
from app.models.runtime import AgentEvent, AgentRun, ProjectRevision
from app.schemas.runtime import (
    AgentFinish,
    ChangeSet,
    ContextItem,
    CreationPlan,
    CreativeContextBundle,
    SelfReview,
    SourceRef,
    ValidationResult,
    KnowledgeRecord,
    PackContext,
)
from app.services.agent.tool_registry import ToolContext, execute_tool, tool_schemas
from app.services.agent_workspace import (
    apply_knowledge_operations,
    collect_file_changes,
    create_run_workspace,
    delete_run_workspace,
    list_run_files,
    read_run_file,
)
from app.services.ai import call_llm
from app.services.memory_client import list_knowledge_records, recall_knowledge
from app.services.memory_config import ensure_project_memory_instance
from app.services.agent.pack_core import load_pack


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["tool_call", "finish"]
    role: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    output: AgentFinish | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "AgentAction":
        if self.action == "tool_call":
            if not self.role or not self.tool:
                raise ValueError("tool_call requires role and tool")
            if self.output is not None:
                raise ValueError("tool_call cannot contain output")
        elif self.output is None:
            raise ValueError("finish requires output")
        return self


class AuditIssue(BaseModel):
    severity: Literal["blocker", "suggestion"]
    evidence: str
    suggestion: str


class AuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    summary: str
    issues: list[AuditIssue] = Field(default_factory=list)


knowledge_record_adapter = TypeAdapter(KnowledgeRecord)


async def append_agent_event(run_id: str, event_type: str, data: dict[str, Any]) -> int:
    async with async_session() as db:
        result = await db.execute(
            select(func.coalesce(func.max(AgentEvent.sequence), 0)).where(
                AgentEvent.run_id == run_id
            )
        )
        sequence = int(result.scalar_one()) + 1
        db.add(
            AgentEvent(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                data=data,
            )
        )
        await db.commit()
    from app.redis import redis_client

    await redis_client.publish(f"agent-run:{run_id}", str(sequence))
    return sequence


async def _load_run_state(run_id: str) -> tuple[AgentRun, TextProject, ProjectRevision | None]:
    async with async_session() as db:
        run_result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = run_result.scalar_one()
        project_result = await db.execute(
            select(TextProject).where(TextProject.id == run.project_id)
        )
        project = project_result.scalar_one()
        revision = None
        if run.base_revision_id:
            revision_result = await db.execute(
                select(ProjectRevision).where(ProjectRevision.id == run.base_revision_id)
            )
            revision = revision_result.scalar_one()
        db.expunge(run)
        db.expunge(project)
        if revision is not None:
            db.expunge(revision)
        return run, project, revision


async def _check_cancelled(run_id: str) -> None:
    async with async_session() as db:
        result = await db.execute(
            select(AgentRun.cancel_requested, AgentRun.status).where(AgentRun.id == run_id)
        )
        cancel_requested, status = result.one()
    if cancel_requested or status == "cancelled":
        raise InterruptedError("Agent run cancelled")


async def _heartbeat(run_id: str, worker_id: str) -> None:
    async with async_session() as db:
        result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalar_one()
        run.heartbeat_at = datetime.now(timezone.utc)
        run.lease_owner = worker_id
        run.lease_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=settings.AGENT_WORKER_LEASE_SECONDS
        )
        await db.commit()


def _resolve_run_model(run: AgentRun, project: TextProject) -> str:
    if run.model:
        return run.model
    component_models = project.component_models or {}
    component = {
        "write": "operation_agent_task",
        "analyze": "operation_analyze",
        "suggest": "operation_agent_suggest",
    }[run.mode]
    model = str(component_models.get(component) or "").strip()
    if not model:
        raise RuntimeError(f"Project model component is not configured: {component}")
    return model


def _read_context_file(run_id: str, path: str) -> ContextItem:
    return ContextItem(
        id=f"file:{path}",
        kind="control_document" if path in {"intent.md", "focus.md", "rules.md", "bible.md"} else "target_file",
        content=read_run_file(run_id, path),
        source_refs=[SourceRef(kind="file", ref=path)],
    )


async def _build_context(
    run: AgentRun,
    project: TextProject,
    revision: ProjectRevision | None,
    knowledge_records: list[dict[str, Any]],
) -> CreativeContextBundle:
    files = [item["path"] for item in list_run_files(run.id)]
    requested = [ref for ref in run.target_refs if ref in files]
    selected = list(dict.fromkeys(
        [name for name in ("intent.md", "focus.md", "rules.md", "bible.md") if name in files]
        + requested
    ))
    if not requested:
        items = [_read_context_file(run.id, path) for path in selected]
        items.append(
            ContextItem(
                id="file-catalog",
                kind="target_file",
                content=json.dumps(files, ensure_ascii=False),
                source_refs=[SourceRef(kind="file", ref=path) for path in files],
            )
        )
    else:
        items = [_read_context_file(run.id, path) for path in selected]
    selected_knowledge: list[dict[str, Any]] = []
    if revision and knowledge_records:
        recalled = await recall_knowledge(
            run.project_id,
            revision.knowledge_dataset,
            run.instruction,
            top_k=12,
        )
        if recalled:
            recall_text = json.dumps(recalled, ensure_ascii=False)
            selected_knowledge = [
                record
                for record in knowledge_records
                if str(record["id"]) in recall_text
                or str(record["title"]) in recall_text
            ]
            if not selected_knowledge:
                raise RuntimeError(
                    "Cognee recall returned context without traceable KnowledgeRecord IDs"
                )
            items.append(
                ContextItem(
                    id=f"recall:{revision.knowledge_dataset}",
                    kind="retrieval",
                    content=json.dumps(recalled, ensure_ascii=False),
                    source_refs=[
                        SourceRef(kind="knowledge", ref=str(record["id"]), revision=revision.id)
                        for record in selected_knowledge
                    ],
                )
            )
    constraints = [
        record
        for record in knowledge_records
        if record.get("kind") == "constraint"
    ]
    selected_by_id = {str(record["id"]): record for record in selected_knowledge}
    for record in constraints:
        selected_by_id[str(record["id"])] = record
    pack = load_pack(project.pack_slug)
    return CreativeContextBundle(
        project_id=run.project_id,
        revision_id=revision.id if revision else None,
        pack_slug=project.pack_slug,
        pack=PackContext(
            default_skills=pack.default_skills,
            auditor_dimensions=pack.auditor_dimensions,
            knowledge_types=pack.knowledge_types,
            unit=pack.unit,
        ),
        target_refs=run.target_refs,
        items=items,
        knowledge=[
            knowledge_record_adapter.validate_python(record)
            for record in selected_by_id.values()
        ],
        constraints=constraints,
    )


async def _llm_json(
    *,
    run: AgentRun,
    model: str,
    prompt: str,
    response_schema: type[BaseModel],
    max_tokens: int,
) -> BaseModel:
    async with async_session() as db:
        response = await call_llm(
            model,
            prompt,
            db,
            max_tokens=max_tokens,
            billing_user_id=run.user_id,
            billing_project_id=run.project_id,
            billing_operation_id=run.id,
            response_schema=response_schema,
            reasoning_effort_override=run.effort,
            prefer_stream_override=False,
        )
        await db.commit()
    return response_schema.model_validate_json(response["content"])


async def _create_plan(
    run: AgentRun,
    model: str,
    context: CreativeContextBundle,
    skill: dict[str, Any],
) -> CreationPlan:
    prompt = (
        "你是 MuseGraph Planner。根据用户目标、项目上下文和当前 Skill 生成严格可执行计划。"
        "计划步骤只能使用当前 Skill.roles 中列出的角色。需要修改文本时必须包含 writer；"
        "需要修改结构化知识时必须包含 updater、memory_builder 或 graph_extractor。"
        "\n\n用户目标：\n"
        f"{run.instruction}\n\nSkill：\n{json.dumps(skill, ensure_ascii=False)}"
        f"\n\n上下文：\n{context.model_dump_json()}"
    )
    return await _llm_json(
        run=run,
        model=model,
        prompt=prompt,
        response_schema=CreationPlan,
        max_tokens=4096,
    )


def _role_context(
    context: CreativeContextBundle,
    role: str,
    instruction: str,
) -> dict[str, Any]:
    if role == "evaluator":
        return {"instruction": instruction, "constraints": [item.model_dump() for item in context.constraints]}
    if role in {"writer", "auditor", "reviser", "updater", "memory_builder", "graph_extractor"}:
        targeted = [
            item.model_dump()
            for item in context.items
            if item.kind in {"control_document", "target_file", "knowledge", "retrieval"}
        ]
        return {
            "instruction": instruction,
            "target_refs": context.target_refs,
            "pack": context.pack.model_dump(mode="json"),
            "items": targeted,
            "knowledge": [item.model_dump() for item in context.knowledge],
            "constraints": [item.model_dump() for item in context.constraints],
        }
    return context.model_dump(mode="json")


async def _run_tool_loop(
    *,
    run: AgentRun,
    model: str,
    plan: CreationPlan,
    context: CreativeContextBundle,
    tool_context: ToolContext,
    skill: dict[str, Any],
    worker_id: str,
    correction: str = "",
) -> AgentFinish:
    history: list[dict[str, Any]] = []
    allowed_tools = set(skill["allowed_tools"])
    if run.mode != "write":
        allowed_tools -= {"write_file", "delete_file", "knowledge_upsert", "knowledge_delete"}
    while True:
        await _check_cancelled(run.id)
        await _heartbeat(run.id, worker_id)
        role = history[-1].get("next_role") if history else None
        if role not in skill["roles"]:
            role = next(
                (step.role for step in plan.steps if step.role in skill["roles"]),
                skill["roles"][0],
            )
        schemas = tool_schemas(allowed_tools, role)
        prompt = (
            "你是 MuseGraph 文本创作 Agent。一次只返回一个严格 JSON action。"
            "tool_call 时填写 role/tool/arguments/reason；完成时 action=finish 并填写 output。"
            "所有写作必须实际调用 write_file，所有结构化知识必须调用 knowledge_upsert/delete。"
            "不得声称未执行的修改。输出语言与用户一致。"
            f"\n\n用户目标：{run.instruction}"
            f"\n\n修订要求：{correction or '无'}"
            f"\n\nSkill：{json.dumps(skill, ensure_ascii=False)}"
            f"\n\n计划：{plan.model_dump_json()}"
            f"\n\n当前角色上下文：{json.dumps(_role_context(context, role, run.instruction), ensure_ascii=False)}"
            f"\n\n当前角色：{role}"
            f"\n\n可用工具：{json.dumps(schemas, ensure_ascii=False)}"
            f"\n\n执行历史：{json.dumps(history, ensure_ascii=False)}"
        )
        action = await _llm_json(
            run=run,
            model=model,
            prompt=prompt,
            response_schema=AgentAction,
            max_tokens=settings.AGENT_PI_TOOL_LOOP_MAX_TOKENS,
        )
        assert isinstance(action, AgentAction)
        if action.action == "finish":
            return action.output
        tool_context.role = str(action.role)
        result = await execute_tool(
            tool_context,
            str(action.tool),
            action.arguments,
            allowed_tools,
        )
        await append_agent_event(
            run.id,
            "tool",
            {
                "role": action.role,
                "tool": action.tool,
                "reason": action.reason,
                "result": result,
            },
        )
        history.append(
            {
                "role": action.role,
                "tool": action.tool,
                "arguments": action.arguments,
                "result": result,
                "next_role": _next_role(plan, len(history)),
            }
        )


def _next_role(plan: CreationPlan, history_length: int) -> str:
    return plan.steps[min(history_length + 1, len(plan.steps) - 1)].role


async def _audit(
    run: AgentRun,
    model: str,
    context: CreativeContextBundle,
    finish: AgentFinish,
    changes: ChangeSet,
) -> AuditResult:
    prompt = (
        "你是只读 MuseGraph Auditor。检查用户目标是否完成、文本是否与结构化知识和约束一致、"
        "是否有明显矛盾。只把必须修复才能满足用户目标的问题标为 blocker；风格优化标为 suggestion。"
        "不得要求额外功能，不得修改文件。"
        f"\n\n用户目标：{run.instruction}"
        f"\n\n上下文：{context.model_dump_json()}"
        f"\n\nAgent完成结果：{finish.model_dump_json()}"
        f"\n\n变更：{changes.model_dump_json()}"
    )
    return await _llm_json(
        run=run,
        model=model,
        prompt=prompt,
        response_schema=AuditResult,
        max_tokens=4096,
    )


def _validate_changes(
    run: AgentRun,
    finish: AgentFinish,
    changes: ChangeSet,
    context_knowledge_ids: set[str],
    required_constraint_ids: set[str],
    required_plan_ids: set[str],
) -> ValidationResult:
    actual_paths = {item.path for item in changes.files}
    declared_paths = set(finish.changed_files)
    checks = [
        {
            "name": "changed_files_match",
            "passed": actual_paths == declared_paths,
            "detail": {
                "actual": sorted(actual_paths),
                "declared": sorted(declared_paths),
            },
        },
        {
            "name": "knowledge_references_exist",
            "passed": set(finish.used_knowledge_ids) <= context_knowledge_ids,
            "detail": {"used_knowledge_ids": finish.used_knowledge_ids},
        },
        {
            "name": "planned_knowledge_is_in_context",
            "passed": required_plan_ids <= context_knowledge_ids,
            "detail": {"required_knowledge_ids": sorted(required_plan_ids)},
        },
        {
            "name": "planned_knowledge_used",
            "passed": required_plan_ids <= set(finish.used_knowledge_ids),
            "detail": {"required_knowledge_ids": sorted(required_plan_ids)},
        },
        {
            "name": "required_constraints_used",
            "passed": run.mode != "write" or required_constraint_ids <= set(finish.used_knowledge_ids),
            "detail": {"required_constraint_ids": sorted(required_constraint_ids)},
        },
        {
            "name": "knowledge_operation_count",
            "passed": finish.knowledge_operations == len(changes.knowledge),
            "detail": {
                "declared": finish.knowledge_operations,
                "actual": len(changes.knowledge),
            },
        },
    ]
    if run.mode == "write":
        checks.append(
            {
                "name": "write_has_changes",
                "passed": bool(changes.files or changes.knowledge),
                "detail": {},
            }
        )
    return ValidationResult(
        passed=all(bool(check["passed"]) for check in checks),
        checks=checks,
    )


async def execute_agent_run(run_id: str, worker_id: str) -> None:
    try:
        run, project, revision = await _load_run_state(run_id)
        model = _resolve_run_model(run, project)
        async with async_session() as memory_db:
            await ensure_project_memory_instance(project, memory_db)
        create_run_workspace(run.project_id, run.id)
        base_records = (
            await list_knowledge_records(run.project_id, revision.knowledge_dataset)
            if revision
            else []
        )
        if base_records:
            async with async_session() as memory_db:
                await ensure_project_memory_instance(project, memory_db, require_models=True)
        knowledge_records = {str(record["id"]): record for record in base_records}
        context = await _build_context(run, project, revision, base_records)
        plan = await _create_plan(run, model, context, run.skill_snapshot)
        invalid_plan_roles = sorted(
            {step.role for step in plan.steps} - set(run.skill_snapshot["roles"])
        )
        if invalid_plan_roles:
            raise ValueError(
                f"CreationPlan uses roles outside the resolved Skill: {invalid_plan_roles}"
            )
        async with async_session() as db:
            record = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
            record.plan = plan.model_dump(mode="json")
            record.context_snapshot = context.model_dump(mode="json")
            await db.commit()
        await append_agent_event(run.id, "plan", plan.model_dump(mode="json"))

        operations: list[Any] = []
        tool_context = ToolContext(
            project_id=run.project_id,
            run_id=run.id,
            role="planner",
            dataset_name=revision.knowledge_dataset if revision else "",
            knowledge_records=knowledge_records,
            knowledge_operations=operations,
        )
        finish = await _run_tool_loop(
            run=run,
            model=model,
            plan=plan,
            context=context,
            tool_context=tool_context,
            skill=run.skill_snapshot,
            worker_id=worker_id,
        )

        if run.mode == "write":
            while True:
                file_changes = collect_file_changes(run.project_id, run.id)
                changes = ChangeSet(files=file_changes, knowledge=operations)
                validation = _validate_changes(
                    run,
                    finish,
                    changes,
                    {item.id for item in context.knowledge}
                    | {item.id for item in context.constraints},
                    {
                        item.id
                        for item in context.constraints
                        if getattr(item, "severity", None) == "required"
                    },
                    set(plan.required_knowledge_ids),
                )
                if not validation.passed:
                    raise RuntimeError(
                        "Deterministic Agent validation failed: "
                        + json.dumps(validation.model_dump(mode="json"), ensure_ascii=False)
                    )
                audit = await _audit(run, model, context, finish, changes)
                blockers = [issue for issue in audit.issues if issue.severity == "blocker"]
                if not blockers:
                    changes.validation = validation
                    changes.self_review = SelfReview(
                        passed=audit.passed,
                        summary=audit.summary,
                        issues=[item.model_dump(mode="json") for item in audit.issues],
                    )
                    break
                correction = json.dumps(
                    [issue.model_dump(mode="json") for issue in blockers],
                    ensure_ascii=False,
                )
                finish = await _run_tool_loop(
                    run=run,
                    model=model,
                    plan=plan,
                    context=context,
                    tool_context=tool_context,
                    skill=run.skill_snapshot,
                    worker_id=worker_id,
                    correction=correction,
                )

            async with async_session() as db:
                record = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
                record.status = "awaiting_review"
                record.final_output = finish.model_dump(mode="json")
                record.change_set = changes.model_dump(mode="json")
                record.validation = changes.validation.model_dump(mode="json")
                record.self_review = changes.self_review.model_dump(mode="json")
                record.lease_owner = None
                record.lease_expires_at = None
                record.heartbeat_at = datetime.now(timezone.utc)
                await db.commit()
            await append_agent_event(
                run.id,
                "awaiting_review",
                {
                    "output": finish.model_dump(mode="json"),
                    "change_set": changes.model_dump(mode="json"),
                },
            )
        else:
            changes = ChangeSet()
            validation = _validate_changes(
                run,
                finish,
                changes,
                {item.id for item in context.knowledge}
                | {item.id for item in context.constraints},
                set(),
                set(plan.required_knowledge_ids),
            )
            if not validation.passed:
                raise RuntimeError(
                    "Deterministic Agent validation failed: "
                    + json.dumps(validation.model_dump(mode="json"), ensure_ascii=False)
                )
            changes.validation = validation
            async with async_session() as db:
                record = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
                record.status = "completed"
                record.final_output = finish.model_dump(mode="json")
                record.change_set = changes.model_dump(mode="json")
                record.validation = validation.model_dump(mode="json")
                record.completed_at = datetime.now(timezone.utc)
                record.lease_owner = None
                record.lease_expires_at = None
                await db.commit()
            await append_agent_event(run.id, "completed", finish.model_dump(mode="json"))
    except InterruptedError:
        delete_run_workspace(run_id)
        async with async_session() as db:
            record = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            record.status = "cancelled"
            record.completed_at = datetime.now(timezone.utc)
            record.lease_owner = None
            record.lease_expires_at = None
            await db.commit()
        await append_agent_event(run_id, "cancelled", {"message": "Agent run cancelled"})
    except Exception as exc:
        delete_run_workspace(run_id)
        async with async_session() as db:
            record = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"
            record.completed_at = datetime.now(timezone.utc)
            record.lease_owner = None
            record.lease_expires_at = None
            await db.commit()
        await append_agent_event(run_id, "failed", {"error": f"{type(exc).__name__}: {exc}"})
        raise

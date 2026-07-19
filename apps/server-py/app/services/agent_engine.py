from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    TypeAdapter,
    ValidationError,
    create_model,
)
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
    CreationPlanStep,
    CreativeBlueprint,
    CreativeContextBundle,
    SelfReview,
    SourceRef,
    ValidationResult,
    KnowledgeRecord,
    PackContext,
)
from app.services.agent.tool_registry import (
    TOOL_REGISTRY,
    DeleteFileInput,
    EmptyInput,
    KnowledgeDeleteInput,
    KnowledgeGetInput,
    KnowledgeSearchInput,
    KnowledgeUpsertInput,
    ReadFileInput,
    ToolContext,
    WriteFileInput,
    execute_tool,
    tool_schemas,
)
from app.services.agent_workspace import (
    apply_knowledge_operations,
    collect_file_changes,
    create_run_workspace,
    delete_run_workspace,
    list_run_files,
    read_run_file,
)
from app.services.ai import call_llm, rerank_knowledge_records
from app.services.memory_client import list_knowledge_records, recall_knowledge
from app.services.memory_config import ensure_project_memory_instance
from app.services.agent.pack_core import load_pack
from app.services.agent.configuration import phase_prompt


AgentRole = Literal[
    "architect",
    "planner",
    "composer",
    "writer",
    "auditor",
    "reviser",
    "evaluator",
    "updater",
    "memory_builder",
    "graph_extractor",
]
PLANNING_ROLES = {
    "writer",
    "evaluator",
    "updater",
    "memory_builder",
    "graph_extractor",
}
EXECUTION_ROLES = PLANNING_ROLES | {"reviser"}
EXECUTION_ROLE_ORDER = (
    "writer",
    "evaluator",
    "updater",
    "memory_builder",
    "graph_extractor",
)


class ToolActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = ""


class ListFilesAction(ToolActionBase):
    action: Literal["list_files"]
    arguments: EmptyInput


class ReadFileAction(ToolActionBase):
    action: Literal["read_file"]
    arguments: ReadFileInput


class WriteFileAction(ToolActionBase):
    action: Literal["write_file"]
    arguments: WriteFileInput


class DeleteFileAction(ToolActionBase):
    action: Literal["delete_file"]
    arguments: DeleteFileInput


class KnowledgeSearchAction(ToolActionBase):
    action: Literal["knowledge_search"]
    arguments: KnowledgeSearchInput


class KnowledgeGetAction(ToolActionBase):
    action: Literal["knowledge_get"]
    arguments: KnowledgeGetInput


class KnowledgeUpsertAction(ToolActionBase):
    action: Literal["knowledge_upsert"]
    arguments: KnowledgeUpsertInput


class KnowledgeDeleteAction(ToolActionBase):
    action: Literal["knowledge_delete"]
    arguments: KnowledgeDeleteInput


ToolCallAction = Annotated[
    ListFilesAction
    | ReadFileAction
    | WriteFileAction
    | DeleteFileAction
    | KnowledgeSearchAction
    | KnowledgeGetAction
    | KnowledgeUpsertAction
    | KnowledgeDeleteAction,
    Field(discriminator="action"),
]
TOOL_ACTION_MODELS = {
    "list_files": ListFilesAction,
    "read_file": ReadFileAction,
    "write_file": WriteFileAction,
    "delete_file": DeleteFileAction,
    "knowledge_search": KnowledgeSearchAction,
    "knowledge_get": KnowledgeGetAction,
    "knowledge_upsert": KnowledgeUpsertAction,
    "knowledge_delete": KnowledgeDeleteAction,
}


class FinishAction(AgentFinish):
    action: Literal["finish"]


class AgentAction(
    RootModel[
        Annotated[
            ListFilesAction
            | ReadFileAction
            | WriteFileAction
            | DeleteFileAction
            | KnowledgeSearchAction
            | KnowledgeGetAction
            | KnowledgeUpsertAction
            | KnowledgeDeleteAction
            | FinishAction,
            Field(discriminator="action"),
        ]
    ]
):
    pass


class PlannerStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    tool: AgentToolName
    plan_unit_ids: list[str] = Field(min_length=1)
    target_refs: list[str] = Field(default_factory=list)
    output_ref: str | None


class PlannerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    steps: list[PlannerStep] = Field(min_length=1)
    required_knowledge_ids: list[str] = Field(default_factory=list)


def _agent_action_schema(
    tool_names: set[str],
    *,
    include_finish: bool = True,
) -> type[RootModel[Any]]:
    action_types = [TOOL_ACTION_MODELS[name] for name in sorted(tool_names)]
    combined_type: Any = action_types[0]
    for action_type in action_types[1:]:
        combined_type |= action_type
    if not include_finish:
        if len(action_types) == 1:
            return RootModel[combined_type]
        return RootModel[
            Annotated[
                combined_type,
                Field(discriminator="action"),
            ]
        ]
    return RootModel[
        Annotated[
            combined_type | FinishAction,
            Field(discriminator="action"),
        ]
    ]


def _creation_plan_schema(
    roles: set[str],
    tool_names: set[str],
) -> type[BaseModel]:
    step_models = []
    for tool_name in sorted(tool_names):
        tool_roles = roles & TOOL_REGISTRY[tool_name].roles
        if not tool_roles:
            continue
        step_models.append(
            create_model(
                f"ResolvedPlannerStep_{tool_name}",
                __base__=PlannerStep,
                tool=(Literal.__getitem__((tool_name,)), ...),
                output_ref=(
                    str if tool_name in {"write_file", "delete_file"} else Literal[None],
                    ...,
                ),
            )
        )
    if not step_models:
        raise ValueError("Resolved Skill has no executable role/tool combinations")
    step_type: Any = step_models[0]
    for step_model in step_models[1:]:
        step_type |= step_model
    if len(step_models) > 1:
        step_type = Annotated[step_type, Field(discriminator="tool")]
    return create_model(
        "ResolvedPlannerResponse",
        __base__=PlannerResponse,
        steps=(list[step_type], Field(min_length=1)),
    )


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
            reranker_model = str(
                (project.component_models or {}).get("memory_reranker") or ""
            ).strip()
            if not reranker_model:
                raise RuntimeError(
                    "Project model component is not configured: memory_reranker"
                )
            async with async_session() as db:
                ranked = await rerank_knowledge_records(
                    reranker_model,
                    run.instruction,
                    selected_knowledge,
                    db,
                )
            selected_knowledge = [record for record, _score in ranked]
            items.append(
                ContextItem(
                    id=f"recall:{revision.knowledge_dataset}",
                    kind="retrieval",
                    content=json.dumps(
                        {
                            "knowledge_ids": [
                                str(record["id"]) for record in selected_knowledge
                            ]
                        },
                        ensure_ascii=False,
                    ),
                    source_refs=[
                        SourceRef(kind="knowledge", ref=str(record["id"]), revision=revision.id)
                        for record in selected_knowledge
                    ],
                )
            )
            items.append(
                ContextItem(
                    id=f"rerank:{reranker_model}",
                    kind="retrieval",
                    content=json.dumps(
                        {
                            "model": reranker_model,
                            "results": [
                                {
                                    "knowledge_id": record["id"],
                                    "relevance_score": score,
                                }
                                for record, score in ranked
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    source_refs=[
                        SourceRef(
                            kind="knowledge",
                            ref=str(record["id"]),
                            revision=revision.id,
                        )
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
    request_prompt = prompt
    while True:
        await _check_cancelled(run.id)
        async with async_session() as db:
            response = await call_llm(
                model,
                (
                    f"{request_prompt}\n\n仅返回符合响应 Schema 的 JSON；"
                    "不得输出分析、Markdown 或任何前后缀。"
                ),
                db,
                max_tokens=max_tokens,
                billing_user_id=run.user_id,
                billing_project_id=run.project_id,
                billing_operation_id=run.id,
                response_schema=response_schema,
                reasoning_effort_override=run.effort,
                prefer_stream_override=True,
            )
            await db.commit()
        try:
            return response_schema.model_validate_json(response["content"])
        except ValidationError as exc:
            errors = exc.errors(include_input=False, include_url=False)
            await append_agent_event(
                run.id,
                "schema_validation_failed",
                {
                    "schema": response_schema.__name__,
                    "errors": errors,
                },
            )
            request_prompt = (
                f"{prompt}\n\n上一次响应未通过严格 Schema 校验，因此没有执行任何工具或"
                "写入。请根据校验错误重新生成完整响应，不要解释，也不要复用截断内容。"
                f"\n\n上一次响应：\n{response['content']}"
                f"\n\n校验错误：\n{json.dumps(errors, ensure_ascii=False)}"
            )


async def _create_plan(
    run: AgentRun,
    project: TextProject,
    model: str,
    context: CreativeContextBundle,
    blueprint: CreativeBlueprint,
    skill: dict[str, Any],
) -> CreationPlan:
    manifest = {
        "target_refs": context.target_refs,
        "control_documents": [
            item.id.removeprefix("file:")
            for item in context.items
            if item.kind == "control_document"
        ],
        "pack_unit": context.pack.unit,
        "knowledge": [
            {"id": item.id, "kind": item.kind, "title": item.title}
            for item in context.knowledge
        ],
        "constraints": [
            {"id": item.id, "title": item.title, "severity": item.severity}
            for item in context.constraints
        ],
        "creative_blueprint": blueprint.model_dump(mode="json"),
    }
    planner_skill = {
        "slug": skill["slug"],
        "roles": skill["roles"],
        "allowed_tools": skill["allowed_tools"],
    }
    prompt = (
        "你是 MuseGraph Planner。根据用户目标、项目上下文和当前 Skill 生成严格可执行计划。"
        "CreativeBlueprint 是已经批准给本次 Run 的创作蓝图；你只负责将每个蓝图单元"
        "映射为执行步骤，不得改写、合并、遗漏或另造蓝图单元。每个步骤的 plan_unit_ids"
        "必须填写该步骤落实的蓝图单元 ID；所有蓝图单元必须被覆盖。"
        "步骤必须严格按 CreativeBlueprint.depends_on_ids 的拓扑顺序排列：一个单元"
        "依赖的全部单元必须出现在它之前，禁止先安排依赖方再安排被依赖方。"
        "每个计划步骤必须且只能对应一次实际工具调用。执行角色由引擎根据 Tool Registry"
        "和当前 Skill 权限确定，计划不得选择或输出 role。每个待写文件必须分别安排一个"
        " tool=write_file 的 writer 步骤；结构化知识变更使用 updater、memory_builder 或"
        " graph_extractor，并在 tool 字段填写该步骤唯一调用的工具。Composer 已将目标"
        "文件、控制文档和知识载入上下文，禁止安排重复的读取或检索步骤。target_refs"
        " 只填写该步骤依赖的输入引用；write_file/delete_file 的唯一输出路径必须填写"
        " output_ref，其他工具的 output_ref 填 null。"
        "计划只描述动作、目标文件和验收意图，禁止在计划中创作正文、大纲或知识内容。"
        "\n\n用户目标：\n"
        f"{run.instruction}\n\nSkill：\n{json.dumps(planner_skill, ensure_ascii=False)}"
        f"\n\n项目清单：\n{json.dumps(manifest, ensure_ascii=False)}"
        + phase_prompt(
            run.agent_snapshot,
            "planner",
            instruction=run.instruction,
            project=project,
        )
    )
    response = await _llm_json(
        run=run,
        model=model,
        prompt=prompt,
        response_schema=_creation_plan_schema(
            set(skill["roles"]) & PLANNING_ROLES,
            set(skill["allowed_tools"])
            & (
                {
                    "write_file",
                    "delete_file",
                    "knowledge_upsert",
                    "knowledge_delete",
                }
                if run.mode == "write"
                else {
                    "list_files",
                    "read_file",
                    "knowledge_search",
                    "knowledge_get",
                }
            ),
        ),
        max_tokens=4096,
    )
    allowed_roles = set(skill["roles"]) & PLANNING_ROLES
    plan = CreationPlan(
        objective=response.objective,
        steps=[
            CreationPlanStep(
                **step.model_dump(),
                role=next(
                    role
                    for role in EXECUTION_ROLE_ORDER
                    if role in allowed_roles and role in TOOL_REGISTRY[step.tool].roles
                ),
            )
            for step in response.steps
        ],
        required_knowledge_ids=response.required_knowledge_ids,
    )
    blueprint_unit_ids = {unit.id for unit in blueprint.units}
    covered_unit_ids = {
        unit_id for step in plan.steps for unit_id in step.plan_unit_ids
    }
    if covered_unit_ids != blueprint_unit_ids:
        raise ValueError(
            "CreationPlan must cover exactly all CreativeBlueprint units: "
            f"expected={sorted(blueprint_unit_ids)}, actual={sorted(covered_unit_ids)}"
        )
    if set(plan.required_knowledge_ids) != set(blueprint.required_knowledge_ids):
        raise ValueError(
            "CreationPlan.required_knowledge_ids must equal "
            "CreativeBlueprint.required_knowledge_ids"
        )
    first_step_by_unit = {
        unit_id: min(
            index
            for index, step in enumerate(plan.steps)
            if unit_id in step.plan_unit_ids
        )
        for unit_id in blueprint_unit_ids
    }
    for unit in blueprint.units:
        late_dependencies = [
            dependency_id
            for dependency_id in unit.depends_on_ids
            if first_step_by_unit[dependency_id] >= first_step_by_unit[unit.id]
        ]
        if late_dependencies:
            raise ValueError(
                f"CreationPlan schedules unit {unit.id} before dependencies: "
                f"{late_dependencies}"
            )
    if run.mode == "write":
        steps_by_unit = {
            unit_id: [
                step
                for step in plan.steps
                if unit_id in step.plan_unit_ids
                and step.tool == "write_file"
                and step.output_ref
            ]
            for unit_id in blueprint_unit_ids
        }
        for unit in blueprint.units:
            if not unit.target_ref:
                raise ValueError(
                    f"Write CreativeBlueprint unit {unit.id} must declare target_ref"
                )
            matching = [
                step
                for step in steps_by_unit[unit.id]
                if step.output_ref == unit.target_ref
            ]
            if len(matching) != 1:
                raise ValueError(
                    f"CreativeBlueprint unit {unit.id} must map to exactly one "
                    f"write_file step for {unit.target_ref}"
                )
    return plan


async def _create_blueprint(
    run: AgentRun,
    project: TextProject,
    model: str,
    context: CreativeContextBundle,
    skill: dict[str, Any],
) -> CreativeBlueprint:
    prompt = (
        "你是 MuseGraph Creative Architect。先完成真正的创作规划，不得调用工具，"
        "不得把“写一个文件”当成创作规划。根据 Text Pack、控制文档、目标文本和"
        "结构化知识，把用户目标拆成可独立验收的内容单元。每个单元必须说明作用、"
        "内容摘要、依赖、使用的 KnowledgeRecord ID 和验收条件；threads 必须追踪"
        "主题、人物弧、论证、谜团、伏笔或约束在单元间的发展。required_knowledge_ids"
        "只能引用上下文中真实存在的知识 ID，并汇总所有单元实际需要的知识。"
        "所有 unit.id 与 thread.id 必须只使用小写 ASCII 字母、数字、下划线或连字符，"
        "必须以小写字母或数字开头，例如 outline、chapter_01、troubleshooting；"
        "禁止把文件名原样作为 ID，禁止大写字母、点、斜杠与中文。"
        "write 模式下，每个内容单元必须给出唯一 target_ref，路径和命名遵循 Pack.unit；"
        "分析或建议模式 target_ref 可以为空。不得在蓝图里创作完整正文。"
        f"\n\n运行模式：{run.mode}"
        f"\n\n用户目标：{run.instruction}"
        f"\n\nSkill：{json.dumps(skill, ensure_ascii=False)}"
        f"\n\n创作上下文：{context.model_dump_json()}"
        + phase_prompt(
            run.agent_snapshot,
            "architect",
            instruction=run.instruction,
            project=project,
        )
    )
    context_ids = {item.id for item in context.knowledge} | {
        item.id for item in context.constraints
    }
    request_prompt = prompt
    while True:
        blueprint = await _llm_json(
            run=run,
            model=model,
            prompt=request_prompt,
            response_schema=CreativeBlueprint,
            max_tokens=8192,
        )
        resolved = CreativeBlueprint.model_validate(blueprint.model_dump())
        try:
            unit_knowledge_ids = {
                knowledge_id
                for unit in resolved.units
                for knowledge_id in unit.knowledge_ids
            }
            if not unit_knowledge_ids <= set(resolved.required_knowledge_ids):
                raise ValueError(
                    "CreativeBlueprint.required_knowledge_ids must include every unit "
                    f"knowledge ID: {sorted(unit_knowledge_ids - set(resolved.required_knowledge_ids))}"
                )
            if run.mode == "write":
                target_refs = [unit.target_ref for unit in resolved.units]
                if len(target_refs) != len(set(target_refs)):
                    raise ValueError("Write CreativeBlueprint target_refs must be unique")
            referenced_ids = set(resolved.required_knowledge_ids) | unit_knowledge_ids
            if not referenced_ids <= context_ids:
                raise ValueError(
                    "CreativeBlueprint references KnowledgeRecord IDs outside "
                    f"CreativeContextBundle: {sorted(referenced_ids - context_ids)}"
                )
            return resolved
        except ValueError as exc:
            await append_agent_event(
                run.id,
                "semantic_validation_failed",
                {"schema": "CreativeBlueprint", "error": str(exc)},
            )
            request_prompt = (
                f"{prompt}\n\n上一次 CreativeBlueprint 虽符合 JSON Schema，但违反运行时"
                "语义约束，因此未执行。请修正后重新提交完整蓝图。"
                f"\n\n上一次蓝图：\n{resolved.model_dump_json()}"
                f"\n\n语义错误：\n{exc}"
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
            if item.kind in {"control_document", "target_file"}
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
    project: TextProject,
    model: str,
    plan: CreationPlan,
    blueprint: CreativeBlueprint,
    context: CreativeContextBundle,
    tool_context: ToolContext,
    skill: dict[str, Any],
    worker_id: str,
    correction: str = "",
) -> AgentFinish:
    history: list[dict[str, Any]] = []
    blueprint_units = {unit.id: unit for unit in blueprint.units}
    allowed_tools = set(skill["allowed_tools"])
    if run.mode != "write":
        allowed_tools -= {"write_file", "delete_file", "knowledge_upsert", "knowledge_delete"}
    while True:
        await _check_cancelled(run.id)
        await _heartbeat(run.id, worker_id)
        current_step = plan.steps[len(history)] if len(history) < len(plan.steps) else None
        role = current_step.role if current_step else plan.steps[-1].role
        schemas = (
            [
                schema
                for schema in tool_schemas(allowed_tools, role)
                if schema["name"] == current_step.tool
            ]
            if current_step
            else []
        )
        if current_step and not schemas:
            raise PermissionError(
                f"Role {role} cannot execute planned tool {current_step.tool}"
            )
        response_schema = (
            _agent_action_schema(
                {current_step.tool},
                include_finish=False,
            )
            if current_step
            else AgentFinish
        )
        protocol_instruction = (
            "当前 write_file 步骤使用正文内容通道，直接创作计划指定的完整文件。"
            if current_step and current_step.tool == "write_file"
            else (
                "一次只返回一个严格 JSON action。调用工具时 action 直接填写工具名，"
                "并填写 arguments/reason。"
                if current_step
                else (
                    "所有计划步骤均已执行。直接返回严格 AgentFinish JSON，填写"
                    " summary、changed_files、knowledge_operations、used_knowledge_ids、"
                    "used_plan_unit_ids 和 unresolved_issues；不要添加 action 外层。"
                )
            )
        )
        grounding_instruction = (
            "当前 Text Pack 是事实型内容。任何具体数字、版本、命令、路径、硬件参数、"
            "前置条件、行为或兼容性结论都必须由角色上下文中的文件或 KnowledgeRecord"
            "直接支持；即使常识上合理，只要上下文没有依据就不得写入。"
            if context.pack_slug in {"product_doc", "paper", "article"}
            else ""
        )
        prompt = (
            f"你是 MuseGraph 文本创作 Agent。{protocol_instruction}"
            "当前计划步骤存在时必须执行且只能执行一次工具调用，不得提前 finish；"
            "当前计划步骤为空时所有步骤均已完成，只能 finish，不得继续调用工具。"
            "finish.used_knowledge_ids 必须至少完整复制计划中的"
            " required_knowledge_ids，并包含角色上下文中的全部 required constraint ID，"
            "不得省略。finish.used_plan_unit_ids 必须完整复制 CreativeBlueprint 的"
            "全部单元 ID，证明每个规划单元都已落实。finish.knowledge_operations 只统计实际执行的"
            " knowledge_upsert 和 knowledge_delete，读取与检索不计入。"
            "所有写作必须实际调用 write_file，所有结构化知识必须调用 knowledge_upsert/delete。"
            "不得声称未执行的修改。输出语言与用户一致。"
            f"{grounding_instruction}"
            f"\n\n用户目标：{run.instruction}"
            f"\n\n修订要求：{correction or '无'}"
            f"\n\nSkill：{json.dumps(skill, ensure_ascii=False)}"
            f"\n\nCreativeBlueprint：{blueprint.model_dump_json()}"
            f"\n\n计划：{plan.model_dump_json()}"
            f"\n\n当前计划步骤：{current_step.model_dump_json() if current_step else '无'}"
            f"\n\n当前角色上下文：{json.dumps(_role_context(context, role, run.instruction), ensure_ascii=False)}"
            f"\n\n当前角色：{role}"
            f"\n\n可用工具：{json.dumps([{'name': schema['name'], 'description': schema['description']} for schema in schemas], ensure_ascii=False)}"
            f"\n\n执行历史：{json.dumps(history, ensure_ascii=False)}"
            + (
                phase_prompt(
                    run.agent_snapshot,
                    role,
                    instruction=run.instruction,
                    project=project,
                )
                if role in {"writer", "reviser"}
                else ""
            )
        )
        if current_step and current_step.tool == "write_file":
            dependency_content: dict[str, str] = {}
            dependency_ids = {
                dependency_id
                for unit_id in current_step.plan_unit_ids
                for dependency_id in blueprint_units[unit_id].depends_on_ids
            }
            for dependency_id in dependency_ids:
                target_ref = blueprint_units[dependency_id].target_ref
                if target_ref:
                    dependency_content[target_ref] = read_run_file(run.id, target_ref)
            async with async_session() as db:
                response = await call_llm(
                    model,
                    (
                        f"{prompt}\n\n直接返回要写入 {current_step.output_ref} 的完整"
                        " UTF-8 Markdown 文件内容。首行必须是章节或文档标题；不得输出"
                        "分析、JSON、代码围栏、工具说明或任何文件内容之外的前后缀。"
                        f"\n\n蓝图依赖单元的当前正文："
                        f"{json.dumps(dependency_content, ensure_ascii=False)}"
                    ),
                    db,
                    max_tokens=settings.AGENT_PI_TOOL_LOOP_MAX_TOKENS,
                    billing_user_id=run.user_id,
                    billing_project_id=run.project_id,
                    billing_operation_id=run.id,
                    reasoning_effort_override=run.effort,
                    prefer_stream_override=True,
                )
                await db.commit()
            if response["content"].lstrip().startswith("```"):
                raise ValueError("Writer returned a Markdown code fence instead of file content")
            action: Any = WriteFileAction(
                action="write_file",
                reason=current_step.goal,
                arguments=WriteFileInput(
                    path=current_step.output_ref,
                    content=response["content"],
                ),
            )
        else:
            action_envelope = await _llm_json(
                run=run,
                model=model,
                prompt=prompt,
                response_schema=response_schema,
                max_tokens=settings.AGENT_PI_TOOL_LOOP_MAX_TOKENS,
            )
            if isinstance(action_envelope, AgentFinish):
                return action_envelope
            action = action_envelope.root
        if isinstance(action, FinishAction):
            return AgentFinish.model_validate(action.model_dump(exclude={"action"}))
        if (
            current_step
            and current_step.tool == "delete_file"
            and action.arguments.path != current_step.output_ref
        ):
            raise ValueError("delete_file arguments.path must match the planned output_ref")
        tool_context.role = role
        result = await execute_tool(
            tool_context,
            action.action,
            action.arguments.model_dump(mode="json"),
            allowed_tools,
        )
        await append_agent_event(
            run.id,
            "tool",
            {
                "role": role,
                "tool": action.action,
                "reason": action.reason,
                "result": result,
            },
        )
        history.append(
            {
                "role": role,
                "tool": action.action,
                "arguments": action.arguments.model_dump(mode="json"),
                "result": result,
            }
        )


async def _audit(
    run: AgentRun,
    project: TextProject,
    model: str,
    context: CreativeContextBundle,
    blueprint: CreativeBlueprint,
    finish: AgentFinish,
    changes: ChangeSet,
) -> AuditResult:
    prompt = (
        "你是只读 MuseGraph Auditor。检查用户目标是否完成、文本是否与结构化知识和约束一致、"
        "是否有明显矛盾。只把必须修复才能满足用户目标的问题标为 blocker；风格优化标为 suggestion。"
        "不得要求额外功能，不得修改文件。对于事实型内容，审核前必须逐项盘点变更中的具体数字、"
        "版本、命令、路径、硬件参数、前置条件、产品行为与兼容性结论，并在上下文文件或"
        " KnowledgeRecord 中找到直接依据；没有直接依据的具体断言即使看似合理也必须标为 blocker。"
        f"\n\n用户目标：{run.instruction}"
        f"\n\nCreativeBlueprint：{blueprint.model_dump_json()}"
        f"\n\n上下文：{context.model_dump_json()}"
        f"\n\nAgent完成结果：{finish.model_dump_json()}"
        f"\n\n变更：{changes.model_dump_json()}"
        + phase_prompt(
            run.agent_snapshot,
            "auditor",
            instruction=run.instruction,
            project=project,
        )
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
    required_blueprint_unit_ids: set[str],
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
            "name": "creative_blueprint_units_used",
            "passed": required_blueprint_unit_ids == set(finish.used_plan_unit_ids),
            "detail": {
                "required_plan_unit_ids": sorted(required_blueprint_unit_ids),
                "used_plan_unit_ids": finish.used_plan_unit_ids,
            },
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
        async with async_session() as db:
            record = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
            record.context_snapshot = context.model_dump(mode="json")
            await db.commit()
        blueprint = await _create_blueprint(
            run,
            project,
            model,
            context,
            run.skill_snapshot,
        )
        async with async_session() as db:
            record = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
            record.creative_plan = blueprint.model_dump(mode="json")
            await db.commit()
        await append_agent_event(
            run.id,
            "creative_plan",
            blueprint.model_dump(mode="json"),
        )
        plan = await _create_plan(
            run,
            project,
            model,
            context,
            blueprint,
            run.skill_snapshot,
        )
        plan_roles = {step.role for step in plan.steps}
        invalid_plan_roles = sorted(
            plan_roles - (set(run.skill_snapshot["roles"]) & PLANNING_ROLES)
        )
        if invalid_plan_roles:
            raise ValueError(
                f"CreationPlan uses roles outside the resolved Skill: {invalid_plan_roles}"
            )
        async with async_session() as db:
            record = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
            record.plan = plan.model_dump(mode="json")
            await db.commit()
        await append_agent_event(
            run.id,
            "execution_plan",
            plan.model_dump(mode="json"),
        )

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
            project=project,
            model=model,
            plan=plan,
            blueprint=blueprint,
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
                    {unit.id for unit in blueprint.units},
                )
                if not validation.passed:
                    raise RuntimeError(
                        "Deterministic Agent validation failed: "
                        + json.dumps(validation.model_dump(mode="json"), ensure_ascii=False)
                    )
                audit = await _audit(
                    run,
                    project,
                    model,
                    context,
                    blueprint,
                    finish,
                    changes,
                )
                blockers = [issue for issue in audit.issues if issue.severity == "blocker"]
                await append_agent_event(
                    run.id,
                    "audit",
                    audit.model_dump(mode="json"),
                )
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
                revision_plan = CreationPlan(
                    objective=f"修复 Auditor 阻塞项：{audit.summary}",
                    steps=[
                        CreationPlanStep(
                            goal=f"根据 Auditor 阻塞项修订：{step.goal}",
                            role="reviser" if step.role == "writer" else step.role,
                            tool=step.tool,
                            plan_unit_ids=step.plan_unit_ids,
                            target_refs=step.target_refs,
                            output_ref=step.output_ref,
                        )
                        for step in plan.steps
                    ],
                    required_knowledge_ids=plan.required_knowledge_ids,
                )
                revision_roles = {step.role for step in revision_plan.steps}
                unavailable_revision_roles = sorted(
                    revision_roles - set(run.skill_snapshot["roles"])
                )
                if unavailable_revision_roles:
                    raise RuntimeError(
                        "Resolved Skill cannot execute Auditor revisions with roles: "
                        f"{unavailable_revision_roles}"
                    )
                finish = await _run_tool_loop(
                    run=run,
                    project=project,
                    model=model,
                    plan=revision_plan,
                    blueprint=blueprint,
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
                {unit.id for unit in blueprint.units},
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

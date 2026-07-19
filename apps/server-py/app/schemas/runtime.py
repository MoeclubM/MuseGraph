from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AgentRunMode = Literal["write", "analyze", "suggest"]
AgentRunStatus = Literal[
    "queued",
    "running",
    "awaiting_review",
    "accepting",
    "completed",
    "rejected",
    "conflicted",
    "failed",
    "cancelled",
]
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
ExecutionAgentRole = Literal[
    "writer",
    "reviser",
    "evaluator",
    "updater",
    "memory_builder",
    "graph_extractor",
]
AgentToolName = Literal[
    "list_files",
    "read_file",
    "write_file",
    "delete_file",
    "knowledge_search",
    "knowledge_get",
    "knowledge_upsert",
    "knowledge_delete",
]
SkillScope = Literal["write", "analyze", "suggest"]
KnowledgeKind = Literal["fact", "entity", "relation", "event", "constraint", "source"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRef(StrictModel):
    kind: Literal["file", "knowledge", "user", "external"]
    ref: str = Field(min_length=1, max_length=1024)
    revision: str | None = Field(default=None, max_length=128)
    excerpt: str | None = Field(default=None, max_length=2000)


class KnowledgeRecordBase(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(min_length=1)
    revision: str | None = Field(default=None, max_length=128)


class FactRecord(KnowledgeRecordBase):
    kind: Literal["fact"]


class EntityRecord(KnowledgeRecordBase):
    kind: Literal["entity"]
    entity_type: str = Field(min_length=1, max_length=120)


class RelationRecord(KnowledgeRecordBase):
    kind: Literal["relation"]
    source_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    predicate: str = Field(min_length=1, max_length=120)


class EventRecord(KnowledgeRecordBase):
    kind: Literal["event"]
    occurred_at: str | None = Field(default=None, max_length=120)


class ConstraintRecord(KnowledgeRecordBase):
    kind: Literal["constraint"]
    severity: Literal["required", "preferred"] = "required"


class SourceRecord(KnowledgeRecordBase):
    kind: Literal["source"]
    locator: str = Field(min_length=1, max_length=2048)


KnowledgeRecord = Annotated[
    FactRecord
    | EntityRecord
    | RelationRecord
    | EventRecord
    | ConstraintRecord
    | SourceRecord,
    Field(discriminator="kind"),
]


class KnowledgeUpsert(StrictModel):
    operation: Literal["upsert"] = "upsert"
    record: KnowledgeRecord


class KnowledgeDelete(StrictModel):
    operation: Literal["delete"] = "delete"
    record_id: str = Field(min_length=1, max_length=128)


KnowledgeOperation = Annotated[
    KnowledgeUpsert | KnowledgeDelete,
    Field(discriminator="operation"),
]


class FileChange(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    change_type: Literal["added", "modified", "deleted"]
    before_hash: str | None = None
    after_hash: str | None = None
    diff: str


class ValidationResult(StrictModel):
    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)


class SelfReview(StrictModel):
    passed: bool
    summary: str
    issues: list[dict[str, Any]] = Field(default_factory=list)


class ChangeSet(StrictModel):
    files: list[FileChange] = Field(default_factory=list)
    knowledge: list[KnowledgeOperation] = Field(default_factory=list)
    validation: ValidationResult | None = None
    self_review: SelfReview | None = None


class CreationPlanStep(StrictModel):
    goal: str = Field(min_length=1)
    role: ExecutionAgentRole
    tool: AgentToolName
    plan_unit_ids: list[str] = Field(min_length=1)
    target_refs: list[str] = Field(default_factory=list)
    output_ref: str | None = None

    @model_validator(mode="after")
    def validate_output_ref(self) -> "CreationPlanStep":
        if self.tool in {"write_file", "delete_file"} and not self.output_ref:
            raise ValueError(f"{self.tool} plan step must declare output_ref")
        if self.tool not in {"write_file", "delete_file"} and self.output_ref:
            raise ValueError(f"{self.tool} plan step cannot declare output_ref")
        return self


class CreationPlan(StrictModel):
    objective: str = Field(min_length=1)
    steps: list[CreationPlanStep] = Field(min_length=1)
    required_knowledge_ids: list[str] = Field(default_factory=list)


class CreativePlanUnit(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=255)
    purpose: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    target_ref: str | None = Field(default=None, max_length=1024)
    depends_on_ids: list[str] = Field(default_factory=list)
    knowledge_ids: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)


class CreativePlanThread(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    kind: Literal[
        "theme",
        "character_arc",
        "argument",
        "mystery",
        "foreshadowing",
        "constraint",
    ]
    description: str = Field(min_length=1)
    introduced_in: list[str] = Field(default_factory=list)
    developed_in: list[str] = Field(default_factory=list)
    resolved_in: list[str] = Field(default_factory=list)


class CreativeBlueprint(StrictModel):
    objective: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    strategy: str = Field(min_length=1)
    units: list[CreativePlanUnit] = Field(min_length=1)
    threads: list[CreativePlanThread] = Field(default_factory=list)
    global_constraints: list[str] = Field(default_factory=list)
    required_knowledge_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "CreativeBlueprint":
        unit_ids = [unit.id for unit in self.units]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("CreativeBlueprint unit IDs must be unique")
        thread_ids = [thread.id for thread in self.threads]
        if len(thread_ids) != len(set(thread_ids)):
            raise ValueError("CreativeBlueprint thread IDs must be unique")
        known = set(unit_ids)
        for unit in self.units:
            unknown = set(unit.depends_on_ids) - known
            if unknown:
                raise ValueError(
                    f"CreativeBlueprint unit {unit.id} has unknown dependencies: {sorted(unknown)}"
                )
            if unit.id in unit.depends_on_ids:
                raise ValueError(f"CreativeBlueprint unit {unit.id} cannot depend on itself")
        for thread in self.threads:
            unknown = (
                set(thread.introduced_in)
                | set(thread.developed_in)
                | set(thread.resolved_in)
            ) - known
            if unknown:
                raise ValueError(
                    f"CreativeBlueprint thread {thread.id} references unknown units: {sorted(unknown)}"
                )
        return self


class ContextItem(StrictModel):
    id: str
    kind: Literal["control_document", "target_file", "knowledge", "retrieval"]
    content: str
    source_refs: list[SourceRef] = Field(min_length=1)


class PackContext(StrictModel):
    default_skills: dict[str, str]
    auditor_dimensions: list[str] = Field(min_length=1)
    knowledge_types: list[KnowledgeKind] = Field(min_length=1)
    unit: dict[str, Any]


class CreativeContextBundle(StrictModel):
    project_id: str
    revision_id: str | None
    pack_slug: str
    pack: PackContext
    target_refs: list[str] = Field(default_factory=list)
    items: list[ContextItem] = Field(default_factory=list)
    knowledge: list[KnowledgeRecord] = Field(default_factory=list)
    constraints: list[KnowledgeRecord] = Field(default_factory=list)


class ResolvedSkillSnapshot(StrictModel):
    slug: str
    name: str
    description: str = ""
    instructions: str
    scopes: list[SkillScope]
    roles: list[AgentRole]
    allowed_tools: list[str]
    params_schema: dict[str, Any] = Field(default_factory=dict)
    default_model_component: str | None = None
    version: int
    source: Literal["builtin", "project"]


class AgentFinish(StrictModel):
    summary: str = Field(min_length=1)
    changed_files: list[str] = Field(default_factory=list)
    knowledge_operations: int = 0
    used_knowledge_ids: list[str] = Field(default_factory=list)
    used_plan_unit_ids: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)


class AgentRunRequest(StrictModel):
    instruction: str = Field(min_length=1, max_length=100_000)
    mode: AgentRunMode = "write"
    agent_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    )
    skill_slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    target_refs: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("target_refs")
    @classmethod
    def unique_target_refs(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class AgentRunResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    user_id: str
    base_revision_id: str | None
    result_revision_id: str | None
    agent_id: str
    mode: AgentRunMode
    status: AgentRunStatus
    instruction: str
    model: str | None
    effort: str | None
    target_refs: list[str]
    creative_plan: dict[str, Any] | None
    plan: dict[str, Any] | None
    context_snapshot: dict[str, Any] | None
    skill_snapshot: dict[str, Any]
    agent_snapshot: dict[str, Any]
    final_output: dict[str, Any] | None
    error: str | None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AgentReviewRequest(StrictModel):
    decision: Literal["accept", "reject"]


class AgentEventResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    event_type: str
    data: dict[str, Any]
    created_at: datetime


class ProjectRevisionResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    parent_revision_id: str | None
    git_commit: str
    knowledge_dataset: str
    created_by_run_id: str | None
    status: Literal["active", "superseded"]
    message: str
    created_at: datetime

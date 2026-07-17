from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class MemoryBuildRequest(BaseModel):
    text: str = ""
    ontology: Optional[dict[str, Any]] = None
    chapter_ids: Optional[list[str]] = None
    build_mode: Literal["rebuild", "incremental"] = "rebuild"

    model_config = {"extra": "forbid"}


class MemoryOntologyGenerateRequest(BaseModel):
    text: str = ""
    requirement: Optional[str] = None
    model: Optional[str] = None
    chapter_ids: Optional[list[str]] = None

    model_config = {"extra": "forbid"}


class MemoryTextIngestRequest(BaseModel):
    text: str = Field(min_length=1)
    source_title: Optional[str] = Field(default=None, max_length=255)
    requirement: Optional[str] = None
    ontology_model: Optional[str] = None
    build_mode: Literal["rebuild", "incremental"] = "rebuild"

    model_config = {"extra": "forbid"}


class MemorySearchRequest(BaseModel):
    query: str
    search_type: Literal[
        "INSIGHTS",
        "SUMMARIES",
        "CHUNKS",
        "MEMORY_COMPLETION",
        "RAG_COMPLETION",
        "MEMORY_SUMMARY_COMPLETION",
    ] = Field(default="INSIGHTS")
    top_k: int = Field(default=10, ge=1, le=50)

    model_config = {"extra": "forbid"}


class MemoryPreviewRequest(BaseModel):
    op_type: Literal[
        "CREATE",
        "CONTINUE",
        "AGENT_TASK",
        "AGENT_SUGGEST",
        "CONSISTENCY_CHECK",
        "ANALYZE",
        "REWRITE",
        "SUMMARIZE",
    ] = "CONTINUE"
    input: str = ""
    workflow_step: Optional[str] = Field(default=None, max_length=64)
    reference_cards: Optional[dict[str, Any]] = None
    include_rendered_context: bool = True

    model_config = {"extra": "forbid"}


class MemoryStatusResponse(BaseModel):
    memory_id: Optional[str] = None
    status: str
    ontology_status: Optional[str] = None
    text_type: Optional[str] = None
    text_type_confidence: Optional[float] = None
    text_type_reason: Optional[str] = None
    memory_freshness: Optional[str] = None
    memory_reason: Optional[str] = None
    memory_changed_count: Optional[int] = None
    memory_added_count: Optional[int] = None
    memory_modified_count: Optional[int] = None
    memory_removed_count: Optional[int] = None
    memory_last_build_at: Optional[str] = None
    memory_mode: Optional[str] = None
    memory_syncing_task_id: Optional[str] = None


class MemoryOntologyResponse(BaseModel):
    status: str
    ontology: dict[str, Any]


class MemoryTaskInfo(BaseModel):
    task_id: str
    task_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    progress: int = 0
    message: str = ""
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    progress_detail: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None


class MemoryTaskStartResponse(BaseModel):
    status: str
    task: MemoryTaskInfo


class MemoryTaskStatusResponse(BaseModel):
    status: str
    task: MemoryTaskInfo


class MemoryTaskListResponse(BaseModel):
    status: str
    tasks: list[MemoryTaskInfo]


class MemoryVisualizationResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class MemoryPreviewResponse(BaseModel):
    status: str
    memory: dict[str, Any]
    rendered_context: Optional[str] = None

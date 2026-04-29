from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GraphBuildRequest(BaseModel):
    text: str = ""
    ontology: Optional[dict[str, Any]] = None
    chapter_ids: Optional[list[str]] = None
    build_mode: Literal["rebuild", "incremental"] = "rebuild"
    resume_failed: bool = False

    model_config = {"extra": "forbid"}


class GraphOntologyGenerateRequest(BaseModel):
    text: str = ""
    requirement: Optional[str] = None
    model: Optional[str] = None
    chapter_ids: Optional[list[str]] = None

    model_config = {"extra": "forbid"}


class GraphOasisAnalyzeRequest(BaseModel):
    text: str = ""
    requirement: Optional[str] = None
    prompt: Optional[str] = None
    analysis_model: Optional[str] = None
    simulation_model: Optional[str] = None
    chapter_ids: Optional[list[str]] = None

    model_config = {"extra": "forbid"}


class GraphOasisPrepareRequest(BaseModel):
    text: str = ""
    requirement: Optional[str] = None
    prompt: Optional[str] = None
    analysis_model: Optional[str] = None
    simulation_model: Optional[str] = None
    chapter_ids: Optional[list[str]] = None

    model_config = {"extra": "forbid"}


class GraphOasisRunRequest(BaseModel):
    package: Optional[dict[str, Any]] = None
    chapter_ids: Optional[list[str]] = None

    model_config = {"extra": "forbid"}


class GraphOasisReportRequest(BaseModel):
    report_model: Optional[str] = None
    chapter_ids: Optional[list[str]] = None

    model_config = {"extra": "forbid"}


class GraphSearchRequest(BaseModel):
    query: str
    search_type: Literal[
        "INSIGHTS",
        "SUMMARIES",
        "CHUNKS",
        "GRAPH_COMPLETION",
        "RAG_COMPLETION",
        "GRAPH_SUMMARY_COMPLETION",
    ] = Field(default="INSIGHTS")
    top_k: int = Field(default=10, ge=1, le=50)
    use_reranker: bool = False
    reranker_model: Optional[str] = None
    reranker_top_n: Optional[int] = Field(default=None, ge=1, le=50)

    model_config = {"extra": "forbid"}


class GraphStatusResponse(BaseModel):
    graph_id: Optional[str] = None
    status: str
    ontology_status: Optional[str] = None
    oasis_status: Optional[str] = None
    graph_freshness: Optional[str] = None
    graph_reason: Optional[str] = None
    graph_changed_count: Optional[int] = None
    graph_added_count: Optional[int] = None
    graph_modified_count: Optional[int] = None
    graph_removed_count: Optional[int] = None
    graph_last_build_at: Optional[str] = None
    graph_mode: Optional[str] = None
    graph_syncing_task_id: Optional[str] = None
    graph_resume_available: Optional[bool] = None
    graph_resume_failed_chunks: Optional[int] = None
    graph_resume_mode: Optional[str] = None


class GraphOntologyResponse(BaseModel):
    status: str
    ontology: dict[str, Any]


class GraphOasisAnalyzeResponse(BaseModel):
    status: str
    analysis: dict[str, Any]
    context: dict[str, Any]


class GraphOasisPrepareResponse(BaseModel):
    status: str
    package: dict[str, Any]


class GraphOasisRunResponse(BaseModel):
    status: str
    run_result: dict[str, Any]


class GraphOasisReportResponse(BaseModel):
    status: str
    report: dict[str, Any]


class GraphTaskInfo(BaseModel):
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


class GraphTaskStartResponse(BaseModel):
    status: str
    task: GraphTaskInfo


class GraphTaskStatusResponse(BaseModel):
    status: str
    task: GraphTaskInfo


class GraphTaskListResponse(BaseModel):
    status: str
    tasks: list[GraphTaskInfo]


class GraphVisualizationResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]

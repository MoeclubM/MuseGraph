from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectFactCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source_kind: str = Field(default="manual", max_length=40)
    source_ref: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}


class ProjectFactUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1)
    source_kind: Optional[str] = Field(default=None, max_length=40)
    source_ref: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}


class ProjectFactResponse(BaseModel):
    id: str
    project_id: str
    created_by_user_id: Optional[str] = None
    created_by_agent_session_id: Optional[str] = None
    source_kind: str
    source_ref: Optional[dict[str, Any]] = None
    title: str
    content: str
    metadata: Optional[dict[str, Any]] = None
    ontology_snapshot: Optional[dict[str, Any]] = None
    entities: Optional[list[dict[str, Any]]] = None
    relationships: Optional[list[dict[str, Any]]] = None
    content_hash: str
    memory_status: str
    memory_task_id: Optional[str] = None
    memory_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProjectFactListResponse(BaseModel):
    facts: list[ProjectFactResponse]


class ProjectFactSyncResponse(BaseModel):
    status: str
    task_id: str
    fact_id: Optional[str] = None


class ProjectEntitySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    entity_type: Optional[str] = Field(default=None, max_length=120)
    limit: int = Field(default=20, ge=1, le=100)

    model_config = {"extra": "forbid"}


class ProjectEntitySearchResult(BaseModel):
    id: str
    name: str
    type: str
    summary: str = ""
    source: str = ""
    fact_id: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ProjectEntitySearchResponse(BaseModel):
    query: str
    total: int
    results: list[ProjectEntitySearchResult]
    categories: list[dict[str, Any]] = Field(default_factory=list)


class ProjectFactEntityBatchItem(BaseModel):
    fact_id: str = Field(min_length=1)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1)
    entities: Optional[list[dict[str, Any]]] = None
    relationships: Optional[list[dict[str, Any]]] = None
    metadata: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}


class ProjectFactBatchUpdateRequest(BaseModel):
    updates: list[ProjectFactEntityBatchItem] = Field(min_length=1)
    structured_memory: Optional[dict[str, Any]] = None
    sync_memory: bool = True

    model_config = {"extra": "forbid"}


class ProjectFactBatchUpdateResponse(BaseModel):
    updated_count: int
    task_id: Optional[str] = None
    facts: list[ProjectFactResponse]

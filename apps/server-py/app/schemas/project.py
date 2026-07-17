from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ProjectChapterCreate(BaseModel):
    title: Optional[str] = Field(default="Main Draft", min_length=1, max_length=255)
    content: str = ""
    status: Literal["planned", "draft", "revised", "final", "archived"] = "draft"
    blueprint: Optional[dict[str, Any]] = None
    plan: Optional[str] = None
    summary: Optional[str] = None
    continuity_notes: Optional[dict[str, Any]] = None
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectChapterUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = None
    status: Optional[Literal["planned", "draft", "revised", "final", "archived"]] = None
    blueprint: Optional[dict[str, Any]] = None
    plan: Optional[str] = None
    summary: Optional[str] = None
    continuity_notes: Optional[dict[str, Any]] = None
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectChapterReorderItem(BaseModel):
    id: str
    order_index: int = Field(ge=0)


class ProjectChapterReorderRequest(BaseModel):
    chapters: list[ProjectChapterReorderItem]


class ProjectChapterResponse(BaseModel):
    id: str
    project_id: str
    title: str
    content: str
    status: str = "draft"
    blueprint: Optional[dict[str, Any]] = None
    plan: Optional[str] = None
    summary: Optional[str] = None
    continuity_notes: Optional[dict[str, Any]] = None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    visibility: Literal["private", "public"] = "private"
    component_models: Optional[dict[str, str]] = None
    operation_prompts: Optional[dict[str, str]] = None
    creative_state: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    component_models: Optional[dict[str, str]] = None
    operation_prompts: Optional[dict[str, str]] = None
    creative_state: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}


class ProjectVisibilityUpdate(BaseModel):
    visibility: Literal["private", "public"]

    model_config = {"extra": "forbid"}


class ProjectMemberCreate(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    role: Literal["viewer", "editor"]

    model_config = {"extra": "forbid"}


class ProjectMemberUpdate(BaseModel):
    role: Literal["viewer", "editor"]

    model_config = {"extra": "forbid"}


class ProjectMemberResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    email: Optional[str] = None
    role: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    visibility: str = "private"
    current_user_role: Optional[str] = None
    current_user_permissions: list[str] = Field(default_factory=list)
    component_models: Optional[dict[str, str]] = None
    operation_prompts: Optional[dict[str, str]] = None
    ontology_schema: Optional[dict[str, Any]] = None
    creative_state: Optional[dict[str, Any]] = None
    memory_id: Optional[str] = None
    chapters: list[ProjectChapterResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectPublicResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    visibility: Literal["public"]
    author_nickname: Optional[str] = None
    current_user_role: Optional[str] = None
    current_user_permissions: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectSearchResult(BaseModel):
    item_type: str
    item_id: str
    title: str
    matched_field: str
    snippet: str
    order_index: int = 0

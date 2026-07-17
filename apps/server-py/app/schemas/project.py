from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Literal["private", "public"] = "private"
    pack_slug: Literal["generic", "novel", "article", "paper", "screenplay", "product_doc"] = "generic"
    component_models: dict[str, str] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    pack_slug: Literal["generic", "novel", "article", "paper", "screenplay", "product_doc"] | None = None
    component_models: dict[str, str] | None = None


class ProjectVisibilityUpdate(BaseModel):
    visibility: Literal["private", "public"]


class ProjectMemberCreate(BaseModel):
    user_id: str
    role: Literal["editor", "viewer"]


class ProjectMemberUpdate(BaseModel):
    role: Literal["editor", "viewer"]


class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    user_id: str
    role: Literal["owner", "editor", "viewer"]
    created_at: datetime
    updated_at: datetime


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    description: str | None
    visibility: Literal["private", "public"]
    component_models: dict[str, str] | None
    active_revision_id: str | None
    memory_instance_id: str | None
    pack_slug: str
    created_at: datetime
    updated_at: datetime
    current_user_role: str | None = None
    current_user_permissions: list[str] = Field(default_factory=list)


class ProjectPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    pack_slug: str
    created_at: datetime
    updated_at: datetime


class ProjectSearchResult(BaseModel):
    items: list[ProjectPublicResponse]
    total: int

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectChapterCreate(BaseModel):
    title: Optional[str] = Field(default="Main Draft", min_length=1, max_length=255)
    content: str = ""
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectChapterUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = None
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
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: Optional[str] = Field(default=None, max_length=255)
    profile: Optional[str] = None
    notes: Optional[str] = None
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectCharacterUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role: Optional[str] = Field(default=None, max_length=255)
    profile: Optional[str] = None
    notes: Optional[str] = None
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectCharacterResponse(BaseModel):
    id: str
    project_id: str
    name: str
    role: Optional[str] = None
    profile: Optional[str] = None
    notes: Optional[str] = None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectGlossaryTermCreate(BaseModel):
    term: str = Field(min_length=1, max_length=255)
    definition: str = ""
    aliases: Optional[list[str]] = None
    notes: Optional[str] = None
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectGlossaryTermUpdate(BaseModel):
    term: Optional[str] = Field(default=None, min_length=1, max_length=255)
    definition: Optional[str] = None
    aliases: Optional[list[str]] = None
    notes: Optional[str] = None
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectGlossaryTermResponse(BaseModel):
    id: str
    project_id: str
    term: str
    definition: str
    aliases: Optional[list[str]] = None
    notes: Optional[str] = None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectWorldbookEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, max_length=120)
    content: str = ""
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectWorldbookEntryUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, max_length=120)
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    order_index: Optional[int] = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ProjectWorldbookEntryResponse(BaseModel):
    id: str
    project_id: str
    title: str
    category: Optional[str] = None
    content: str
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    simulation_requirement: Optional[str] = None
    component_models: Optional[dict[str, str]] = None

    model_config = {"extra": "forbid"}


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    simulation_requirement: Optional[str] = None
    component_models: Optional[dict[str, str]] = None
    oasis_analysis: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}


class ProjectResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    simulation_requirement: Optional[str] = None
    component_models: Optional[dict[str, str]] = None
    ontology_schema: Optional[dict[str, Any]] = None
    oasis_analysis: Optional[dict[str, Any]] = None
    cognee_dataset_id: Optional[str] = None
    chapters: list[ProjectChapterResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OperationRequest(BaseModel):
    type: str  # CREATE / CONTINUE / ANALYZE / REWRITE / SUMMARIZE
    input: Optional[str] = None
    model: Optional[str] = None
    chapter_ids: Optional[list[str]] = None
    character_ids: Optional[list[str]] = None
    glossary_term_ids: Optional[list[str]] = None
    worldbook_entry_ids: Optional[list[str]] = None
    use_rag: Optional[bool] = None

    model_config = {"extra": "forbid"}


class OperationResponse(BaseModel):
    id: str
    project_id: str
    type: str
    input: Optional[str] = None
    output: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    status: str
    error: Optional[str] = None
    progress: int = 0
    message: Optional[str] = None
    metadata: Optional[dict[str, Any]] = Field(None, alias="metadata_", validation_alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

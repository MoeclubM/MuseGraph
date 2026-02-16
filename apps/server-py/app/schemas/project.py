from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    content: Optional[str] = None
    simulation_requirement: Optional[str] = None
    component_models: Optional[dict[str, str]] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    content: Optional[str] = None
    simulation_requirement: Optional[str] = None
    component_models: Optional[dict[str, str]] = None
    oasis_analysis: Optional[dict[str, Any]] = None


class ProjectResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    simulation_requirement: Optional[str] = None
    component_models: Optional[dict[str, str]] = None
    ontology_schema: Optional[dict[str, Any]] = None
    oasis_analysis: Optional[dict[str, Any]] = None
    cognee_dataset_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OperationRequest(BaseModel):
    type: str  # CREATE / CONTINUE / ANALYZE / REWRITE / SUMMARIZE
    input: Optional[str] = None
    model: Optional[str] = None


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

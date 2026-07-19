from datetime import datetime
import re
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from app.schemas.runtime import StrictModel


PromptPhase = Literal["architect", "planner", "writer", "auditor", "reviser"]
PROMPT_PHASES = {"architect", "planner", "writer", "auditor", "reviser"}
PROMPT_VARIABLES = {
    "instruction",
    "project_title",
    "project_description",
    "pack_slug",
    "agent_name",
}


def validate_prompt_content(value: str | None) -> str:
    if value is None:
        raise ValueError("Prompt template content cannot be null")
    variables = set(re.findall(r"\{\{([^{}]+)\}\}", value))
    unknown = variables - PROMPT_VARIABLES
    if unknown:
        raise ValueError(f"Unknown prompt template variables: {sorted(unknown)}")
    return value


class PromptTemplateCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    phase: PromptPhase
    content: str = Field(min_length=1, max_length=100_000)

    _validate_content = field_validator("content")(validate_prompt_content)


class PromptTemplateUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    phase: PromptPhase | None = None
    content: str | None = Field(default=None, min_length=1, max_length=100_000)

    _validate_content = field_validator("content")(validate_prompt_content)

    @field_validator("name", "description", "phase")
    @classmethod
    def reject_null_fields(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Prompt template field cannot be null")
        return value


class PromptTemplateResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    description: str
    phase: PromptPhase
    content: str
    version: int
    created_at: datetime
    updated_at: datetime


class PromptTemplateSnapshot(StrictModel):
    id: str
    name: str
    phase: PromptPhase
    content: str
    version: int


class ProjectAgentCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    model: str | None = Field(default=None, max_length=160)
    effort: Literal["low", "medium", "high"] | None = None
    prompt_template_ids: dict[PromptPhase, str] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class ProjectAgentUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    model: str | None = Field(default=None, max_length=160)
    effort: Literal["low", "medium", "high"] | None = None
    prompt_template_ids: dict[PromptPhase, str] | None = None
    enabled: bool | None = None

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("name", "description", "prompt_template_ids", "enabled")
    @classmethod
    def reject_null_fields(cls, value):
        if value is None:
            raise ValueError("Project Agent field cannot be null")
        return value


class ProjectAgentResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    created_by_user_id: str
    name: str
    description: str
    model: str | None
    effort: str | None
    prompt_template_ids: dict[str, str]
    version: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ProjectAgentSnapshot(StrictModel):
    id: str
    name: str
    description: str
    model: str | None
    model_source: Literal["agent", "project_component"] | None
    effort: Literal["low", "medium", "high"] | None
    version: int
    prompt_templates: dict[PromptPhase, PromptTemplateSnapshot]

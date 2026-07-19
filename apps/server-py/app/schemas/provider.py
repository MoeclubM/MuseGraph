from datetime import datetime

from pydantic import ConfigDict, Field, SecretStr, field_validator

from app.schemas.runtime import StrictModel


def _normalize_models(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class UserProviderCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=50)
    api_key: SecretStr
    base_url: str | None = Field(default=None, max_length=500)
    models: list[str] = Field(default_factory=list)
    embedding_models: list[str] = Field(default_factory=list)
    reranker_models: list[str] = Field(default_factory=list)
    is_active: bool = True
    priority: int = Field(default=0, ge=-1000, le=1000)

    _normalize_model_lists = field_validator(
        "models",
        "embedding_models",
        "reranker_models",
    )(_normalize_models)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("API key cannot be empty")
        return value


class UserProviderUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider: str | None = Field(default=None, min_length=1, max_length=50)
    api_key: SecretStr | None = None
    base_url: str | None = Field(default=None, max_length=500)
    models: list[str] | None = None
    embedding_models: list[str] | None = None
    reranker_models: list[str] | None = None
    is_active: bool | None = None
    priority: int | None = Field(default=None, ge=-1000, le=1000)

    @field_validator("models", "embedding_models", "reranker_models")
    @classmethod
    def normalize_model_lists(cls, value: list[str] | None) -> list[str]:
        if value is None:
            raise ValueError("Provider model lists cannot be null")
        return _normalize_models(value)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr | None) -> SecretStr:
        if value is None or not value.get_secret_value().strip():
            raise ValueError("API key cannot be empty")
        return value

    @field_validator("name", "provider", "is_active", "priority")
    @classmethod
    def reject_null_fields(cls, value):
        if value is None:
            raise ValueError("Provider field cannot be null")
        return value


class UserProviderResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider: str
    base_url: str | None
    models: list[str]
    embedding_models: list[str]
    reranker_models: list[str]
    is_active: bool
    priority: int
    has_api_key: bool
    created_at: datetime
    updated_at: datetime

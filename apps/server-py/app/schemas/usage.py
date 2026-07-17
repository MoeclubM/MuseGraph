from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class UsageRecordItem(BaseModel):
    id: str
    user_id: str
    user_email: Optional[str] = None
    user_nickname: Optional[str] = None
    project_id: Optional[str] = None
    project_title: Optional[str] = None
    operation_id: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    billing_mode: Optional[str] = None
    request_id: Optional[str] = None
    status: str = "SUCCESS"
    source: str = "llm"
    metadata: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None


class UsageRecordListResponse(BaseModel):
    records: list[UsageRecordItem]
    total: int
    page: int
    page_size: int


class UsageRetentionConfig(BaseModel):
    retention_days: Optional[int] = Field(default=None, description="null = no age limit")
    max_records: Optional[int] = Field(default=None, description="null = no count limit")
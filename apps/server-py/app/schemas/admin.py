from typing import Any

from pydantic import BaseModel, Field


class DailyUsagePoint(BaseModel):
    date: str
    request_count: int = 0
    active_users: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


class TopUserUsage(BaseModel):
    user_id: str
    email: str
    nickname: str | None = None
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


class TopModelUsage(BaseModel):
    model: str
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


class UsageAuditSummary(BaseModel):
    usage_without_operation: int = 0
    usage_without_project: int = 0
    usage_with_missing_operation_record: int = 0
    usage_with_missing_project_record: int = 0
    usage_with_project_user_mismatch: int = 0
    usage_with_operation_user_mismatch: int = 0
    usage_operation_value_mismatch: int = 0
    negative_balance_users: int = 0


class StatsResponse(BaseModel):
    total_users: int = 0
    total_projects: int = 0
    total_operations: int = 0
    completed_operations: int = 0
    failed_operations: int = 0
    total_revenue: float = 0.0
    total_usage_cost: float = 0.0
    total_balance: float = 0.0
    average_balance: float = 0.0
    total_request_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    daily_active_users: int = 0
    last_24h_request_count: int = 0
    last_24h_cost: float = 0.0
    last_24h_input_tokens: int = 0
    last_24h_output_tokens: int = 0
    last_24h_tokens: int = 0
    last_7d_cost: float = 0.0
    last_30d_cost: float = 0.0
    top_users: list[TopUserUsage] = Field(default_factory=list)
    top_models: list[TopModelUsage] = Field(default_factory=list)
    daily_usage: list[DailyUsagePoint] = Field(default_factory=list)
    usage_audit: UsageAuditSummary = Field(default_factory=UsageAuditSummary)


class UserListResponse(BaseModel):
    users: list[dict[str, Any]]
    total: int
    page: int
    page_size: int

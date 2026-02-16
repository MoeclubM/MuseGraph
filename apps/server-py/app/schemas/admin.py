from typing import Any

from pydantic import BaseModel


class StatsResponse(BaseModel):
    total_users: int = 0
    total_projects: int = 0
    total_operations: int = 0
    total_revenue: float = 0.0
    daily_active_users: int = 0


class UserListResponse(BaseModel):
    users: list[dict[str, Any]]
    total: int
    page: int
    page_size: int

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    email: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    balance: float
    is_admin: bool
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUsageResponse(BaseModel):
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    daily_requests: int = 0
    monthly_requests: int = 0

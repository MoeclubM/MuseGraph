from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    nickname: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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


class AuthResponse(BaseModel):
    user: UserResponse
    token: str

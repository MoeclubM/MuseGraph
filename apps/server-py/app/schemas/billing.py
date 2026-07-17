from typing import Optional

from pydantic import BaseModel, Field


class PricingRuleResponse(BaseModel):
    id: Optional[str] = None
    model: str
    model_type: str = "chat"
    providers: list[str] = Field(default_factory=list)
    has_pricing: bool = True
    billing_mode: str = "TOKEN"
    input_price: float = 0.0
    output_price: float = 0.0
    token_unit: int = 1000000
    request_price: float = 0.0
    is_active: bool = True

    model_config = {"from_attributes": True}


class BalanceResponse(BaseModel):
    balance: float
    daily_usage: float = 0.0
    monthly_usage: float = 0.0


class DepositRequest(BaseModel):
    amount: float
    payment_method: Optional[str] = None

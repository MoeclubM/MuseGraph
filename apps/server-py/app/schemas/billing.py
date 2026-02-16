from typing import Optional

from pydantic import BaseModel


class PricingRuleResponse(BaseModel):
    id: str
    model: str
    input_price: float
    output_price: float

    model_config = {"from_attributes": True}


class BalanceResponse(BaseModel):
    balance: float
    daily_usage: float = 0.0
    monthly_usage: float = 0.0


class DepositRequest(BaseModel):
    amount: float
    payment_method: Optional[str] = None

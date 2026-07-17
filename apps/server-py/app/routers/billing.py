from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.billing import BalanceResponse, DepositRequest, PricingRuleResponse
from app.services.billing import create_deposit, get_daily_usage, get_monthly_usage
from app.services.pricing_catalog import collect_pricing_catalog

router = APIRouter()


@router.get("/pricing", response_model=list[PricingRuleResponse])
async def get_pricing(db: AsyncSession = Depends(get_db)):
    rows = await collect_pricing_catalog(db, provider_active_only=True, pricing_active_only=True)
    return [PricingRuleResponse(**row) for row in rows]


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    daily = await get_daily_usage(user.id, db)
    monthly = await get_monthly_usage(user.id, db)
    return BalanceResponse(
        balance=float(user.balance),
        daily_usage=float(daily),
        monthly_usage=float(monthly),
    )


@router.post("/deposit")
async def deposit(
    body: DepositRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dep = await create_deposit(user.id, body.amount, body.payment_method, db)
    return {"id": dep.id, "amount": float(dep.amount), "status": dep.status}

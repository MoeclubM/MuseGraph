from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.billing import Usage
from app.models.user import User
from app.schemas.usage import UsageRecordListResponse
from app.schemas.user import UserResponse, UserUsageResponse
from app.services.usage_records import list_usage_records

router = APIRouter()


@router.get("/me/usage/details", response_model=UsageRecordListResponse)
async def get_my_usage_details(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    model: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_usage_records(
        db,
        user_id=current_user.id,
        model=model,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        include_project=True,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.get("/{user_id}/usage", response_model=UserUsageResponse)
async def get_user_usage(user_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Total stats
    total_result = await db.execute(
        select(
            func.count(Usage.id),
            func.coalesce(func.sum(Usage.input_tokens + Usage.output_tokens), 0),
            func.coalesce(func.sum(Usage.cost), 0),
        ).where(Usage.user_id == user_id)
    )
    total_row = total_result.one()

    # Daily count
    daily_result = await db.execute(
        select(func.count(Usage.id)).where(
            Usage.user_id == user_id, Usage.created_at >= today_start
        )
    )
    daily_count = daily_result.scalar() or 0

    # Monthly count
    monthly_result = await db.execute(
        select(func.count(Usage.id)).where(
            Usage.user_id == user_id, Usage.created_at >= month_start
        )
    )
    monthly_count = monthly_result.scalar() or 0

    return UserUsageResponse(
        total_requests=int(total_row[0]),
        total_tokens=int(total_row[1]),
        total_cost=float(total_row[2]),
        daily_requests=daily_count,
        monthly_requests=monthly_count,
    )


@router.get("/{user_id}/usage/details", response_model=UsageRecordListResponse)
async def get_user_usage_details(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    model: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return await list_usage_records(
        db,
        user_id=user_id,
        model=model,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        include_project=True,
    )

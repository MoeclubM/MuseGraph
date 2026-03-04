from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth import create_session, delete_session, register_user, verify_password

router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(body.email, body.password, body.nickname, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    token = await create_session(user.id, db)
    response.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return AuthResponse(user=UserResponse.model_validate(user), token=token)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    token = await create_session(user.id, db)
    response.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return AuthResponse(user=UserResponse.model_validate(user), token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    token = (
        request.cookies.get("session_token")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    if token:
        await delete_session(token, db)
    response.delete_cookie("session_token")
    return None


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)

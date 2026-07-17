from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_session, get_current_user
from app.models.user import Session, User
from app.models.runtime import AuditLog
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UpdateMeRequest,
    UserResponse,
)
from app.services.auth import (
    create_session,
    delete_session,
    hash_password,
    register_user,
    revoke_user_sessions,
    verify_password,
)
from app.services.rate_limit import enforce_rate_limit

router = APIRouter()


def _set_session_cookies(response: Response, token: str, csrf_token: str) -> None:
    max_age = settings.SESSION_EXPIRES_HOURS * 3600
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        "musegraph_csrf",
        csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(
        f"auth:register:{request.client.host if request.client else 'unknown'}",
        settings.AUTH_RATE_LIMIT_PER_MINUTE,
    )
    try:
        user = await register_user(body.email, body.password, body.nickname, db)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    token, csrf_token = await create_session(user.id, db)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="auth.register",
            target_type="user",
            target_id=user.id,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
            detail={},
        )
    )
    await db.commit()
    request.state.actor_user_id = user.id
    _set_session_cookies(response, token, csrf_token)
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(
        f"auth:login:{request.client.host if request.client else 'unknown'}:{body.email.lower()}",
        settings.AUTH_RATE_LIMIT_PER_MINUTE,
    )
    result = await db.execute(select(User).where(User.email == body.email.strip().lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        db.add(
            AuditLog(
                action="auth.login.failed",
                target_type="user_email",
                target_id=body.email.strip().lower(),
                request_id=getattr(request.state, "request_id", None),
                ip_address=request.client.host if request.client else None,
                detail={},
            )
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    token, csrf_token = await create_session(user.id, db)
    request.state.actor_user_id = user.id
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="auth.login.succeeded",
            target_type="user",
            target_id=user.id,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
            detail={},
        )
    )
    _set_session_cookies(response, token, csrf_token)
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        await delete_session(token, db)
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie("musegraph_csrf", path="/")
    return None


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateMeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.nickname is not None:
        user.nickname = body.nickname
    if body.email is not None:
        normalized = body.email.strip().lower()
        result = await db.execute(select(User).where(User.email == normalized, User.id != user.id))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        user.email = normalized
    await db.flush()
    return UserResponse.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(
        f"auth:change-password:{user.id}",
        settings.AUTH_RATE_LIMIT_PER_MINUTE,
    )
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    await revoke_user_sessions(user.id, db)
    return None

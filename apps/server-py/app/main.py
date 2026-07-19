from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.models  # noqa: F401
from app.config import settings
from app.database import async_session
from app.redis import redis_client
from app.services.agent.skills import validate_pack_skill_references
from app.storage import ensure_bucket

logger = logging.getLogger(__name__)


def _validate_runtime_security() -> None:
    if settings.REGISTRATION_MODE not in {"open", "invite", "disabled"}:
        raise RuntimeError("REGISTRATION_MODE must be open, invite, or disabled")
    if settings.APP_ENV == "production":
        if not settings.COOKIE_SECURE:
            raise RuntimeError("COOKIE_SECURE must be enabled in production")
        if not settings.SECRET_ENCRYPTION_KEY:
            raise RuntimeError("SECRET_ENCRYPTION_KEY is required in production")
        if not settings.INTERNAL_SERVICE_TOKEN:
            raise RuntimeError("INTERNAL_SERVICE_TOKEN is required in production")
        if settings.REGISTRATION_MODE == "open":
            raise RuntimeError("Open unverified registration is not allowed in production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_runtime_security()
    validate_pack_skill_references()
    ensure_bucket()
    if settings.AUTO_SEED_DATA:
        from seed import seed

        await seed()
    yield


app = FastAPI(title="MuseGraph API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    response = await call_next(request)
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and response.status_code < 400
        and getattr(request.state, "actor_user_id", None)
    ):
        from app.models.runtime import AuditLog

        async with async_session() as db:
            db.add(
                AuditLog(
                    actor_user_id=request.state.actor_user_id,
                    action=f"http.{request.method.lower()}",
                    target_type="api",
                    target_id=request.url.path,
                    request_id=request.state.request_id,
                    ip_address=request.client.host if request.client else None,
                    detail={"status_code": response.status_code},
                )
            )
            await db.commit()
    response.headers["X-Request-Id"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-Id", "Last-Event-ID"],
)

from app.routers import (  # noqa: E402
    admin,
    agent,
    ai,
    auth,
    billing,
    export,
    memory,
    payment,
    project_files,
    project_agents,
    project_versions,
    projects,
    prompt_templates,
    skills,
    users,
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(
    prompt_templates.router,
    prefix="/api/users/me/prompt-templates",
    tags=["prompt-templates"],
)
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(
    project_agents.router,
    prefix="/api/projects/{project_id}/agents",
    tags=["project-agents"],
)
app.include_router(project_files.router, prefix="/api/projects/{project_id}/files", tags=["project-files"])
app.include_router(project_versions.router, prefix="/api/projects/{project_id}/versions", tags=["project-versions"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(payment.router, prefix="/api/payment", tags=["payment"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(agent.router, prefix="/api/projects/{project_id}/agent", tags=["agent"])
app.include_router(skills.router, prefix="/api/projects/{project_id}/skills", tags=["skills"])
app.include_router(memory.router, prefix="/api/projects/{project_id}/memory", tags=["memory"])
app.include_router(export.router, prefix="/api/projects/{project_id}/export", tags=["export"])


@app.get("/api/health")
async def health():
    async with async_session() as db:
        await db.execute(text("SELECT 1"))
    await redis_client.ping()
    return {"status": "ok"}

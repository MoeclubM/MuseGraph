from contextlib import asynccontextmanager
import logging

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.storage import ensure_bucket
import app.models  # noqa: F401 — register all models with Base.metadata

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure local storage root
    ensure_bucket()

    # Run seed only when explicitly enabled
    if settings.AUTO_SEED_DATA:
        try:
            from seed import seed
            await seed()
        except Exception as e:
            logger.warning(f"Seed failed: {e}")

    try:
        from app.database import async_session
        from app.services.usage_retention import enforce_usage_retention

        try:
            async with async_session() as session:
                await enforce_usage_retention(session)
                await session.commit()
        except Exception as e:
            logger.warning("Usage retention cleanup on startup failed: %s", e)

        try:
            from app.routers.agent import reconcile_stale_agent_sessions

            n = await reconcile_stale_agent_sessions()
            if n:
                logger.warning("Reconciled %s stale agent session(s) on startup", n)
        except Exception as e:
            logger.warning("Agent stale-session reconcile on startup failed: %s", e)

        yield
    finally:
        from app.services.memory_backend import close_runtime

        await close_runtime()


app = FastAPI(title="MuseGraph API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL, "http://localhost:3000", "http://localhost:3010", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import (  # noqa: E402
    admin,
    agent,
    ai,
    auth,
    billing,
    export,
    facts,
    memory,
    payment,
    project_files,
    project_versions,
    projects,
    skills,
    users,
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(project_files.router, prefix="/api/projects/{project_id}/files", tags=["project-files"])
app.include_router(project_versions.router, prefix="/api/projects/{project_id}/versions", tags=["project-versions"])
app.include_router(facts.router, prefix="/api/projects/{project_id}/facts", tags=["facts"])
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
    return {"status": "ok"}

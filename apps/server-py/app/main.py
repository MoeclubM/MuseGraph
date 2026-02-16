from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.storage import ensure_bucket
import app.models  # noqa: F401 — register all models with Base.metadata

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Ensure MinIO bucket
    ensure_bucket()

    # Initialize Cognee
    try:
        from app.services.cognee import setup_cognee
        await setup_cognee()
    except Exception:
        pass

    # Run seed only when explicitly enabled
    if settings.AUTO_SEED_DATA:
        try:
            from seed import seed
            await seed()
        except Exception as e:
            logger.warning(f"Seed failed: {e}")

    yield
    # Shutdown


app = FastAPI(title="MuseGraph API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import (  # noqa: E402
    admin,
    ai,
    auth,
    billing,
    cognee_graph,
    export,
    groups,
    payment,
    projects,
    users,
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
app.include_router(payment.router, prefix="/api/payment", tags=["payment"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(cognee_graph.router, prefix="/api/projects/{project_id}/graphs", tags=["graphs"])
app.include_router(export.router, prefix="/api/projects/{project_id}/export", tags=["export"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}

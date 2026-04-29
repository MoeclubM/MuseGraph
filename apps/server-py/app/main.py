from contextlib import asynccontextmanager
import logging

import uuid

from fastapi import FastAPI, Request
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

    # Ensure local storage root
    ensure_bucket()

    # Initialize graph runtime
    try:
        from app.services.graph_service import setup_graph_runtime

        await setup_graph_runtime()
    except Exception as exc:
        logger.exception("Graph runtime initialization failed")
        raise RuntimeError("Graph runtime initialization failed") from exc

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
    ai,
    auth,
    billing,
    export,
    graph,
    payment,
    projects,
    report,
    simulation,
    users,
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(payment.router, prefix="/api/payment", tags=["payment"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(graph.router, prefix="/api/projects/{project_id}/graphs", tags=["graphs"])
app.include_router(export.router, prefix="/api/projects/{project_id}/export", tags=["export"])
app.include_router(simulation.router, prefix="/api/simulation", tags=["simulation"])
app.include_router(report.router, prefix="/api/report", tags=["report"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}

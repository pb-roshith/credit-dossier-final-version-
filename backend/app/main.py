"""
FastAPI application entry point.
Mounts all routers and configures CORS for frontend integration.
"""

# CRITICAL: Override system-level OTEL_SDK_DISABLED=true BEFORE any OTel imports.
# Without this, all TracerProviders return NoOpTracer and no traces are exported.
import os
os.environ["OTEL_SDK_DISABLED"] = "false"

# Load .env into OS environment — Mistral SDK reads MISTRAL_SDK_TELEMETRY
# from os.environ (pydantic-settings only loads into its own model, not os.environ)
from dotenv import load_dotenv
load_dotenv()

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.models import Deal, Section, AuditEntry, Version, Upload  # noqa: F401
from app.models import DealDocument, SectionDocumentLink  # noqa: F401 — register models
from app.models import MistralAgent, LibraryFile  # noqa: F401 — register new models
from app.routers.deals import router as deals_router
from app.routers.sections import router as sections_router
from app.routers.versions import router as versions_router
from app.routers.uploads import router as uploads_router
from app.routers.exports import router as exports_router
from app.routers.documents import router as documents_router
from app.routers.library import router as library_router
from app.routers.mcp import router as mcp_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables, connect MCP, and initialize global agents."""
    import time

    t0 = time.time()
    logger.info("=== Credit Dossier API Starting ===")
    from app.telemetry import init_phoenix_telemetry
    init_phoenix_telemetry(project_name="credit-dossier-api")

    # Step 1: Database
    t_step = time.time()
    logger.info("[startup] Creating database tables…")
    Base.metadata.create_all(bind=engine)
    logger.info(f"[startup] Database ready ({(time.time() - t_step)*1000:.0f}ms)")

    from app.database import SessionLocal
    from app.services.mistral_library_service import MistralLibraryService
    from app.services.mcp_service import MCPClientService
    from app.config import settings

    # Step 2: MCP connection (graceful — don't crash if unreachable)
    t_step = time.time()
    logger.info("[startup] Connecting to MCP server…")
    try:
        await MCPClientService.connect()
        logger.info(f"[startup] MCP connected ({(time.time() - t_step)*1000:.0f}ms)")
    except Exception as e:
        logger.warning(
            f"[startup] MCP connection failed ({(time.time() - t_step)*1000:.0f}ms): {e}. "
            f"Continuing without MCP — orchestration will use library RAG only."
        )

    # Step 3: Mistral Agents (16 section + 1 orchestration)
    t_step = time.time()
    db = SessionLocal()
    try:
        logger.info("[startup] Initializing Mistral agents…")
        await MistralLibraryService.initialize_global_agents(db)
        logger.info(f"[startup] Agents ready ({(time.time() - t_step)*1000:.0f}ms)")
    finally:
        db.close()

    total_ms = (time.time() - t0) * 1000

    # Report telemetry status
    from app.telemetry import is_telemetry_enabled
    telemetry_status = 'enabled' if is_telemetry_enabled() else 'disabled'

    logger.info(
        f"=== Startup complete in {total_ms:.0f}ms ==="
        f" | MCP={'connected' if MCPClientService.is_connected else 'disconnected'}"
        f" | Orchestration={'enabled' if settings.ORCHESTRATION_ENABLED else 'disabled'}"
        f" | Telemetry={telemetry_status}"
        f" | Gen semaphore={settings.GENERATION_SEMAPHORE}"
        f" | Orch semaphore={settings.ORCHESTRATION_SEMAPHORE}"
    )

    yield

    logger.info("=== Shutting down ===")
    db = SessionLocal()
    try:
        await MistralLibraryService.cleanup_global_agents(db)
        await MCPClientService.disconnect()
    finally:
        db.close()
    logger.info("=== Shutdown complete ===")


app = FastAPI(
    title="Credit Dossier API",
    description="Backend API for the Credit Pitch Book Pipeline — deals, narratives, exports.",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routers ───────────────────────────────────────────────
app.include_router(deals_router)
app.include_router(sections_router)
app.include_router(versions_router)
app.include_router(uploads_router)
app.include_router(exports_router)
app.include_router(documents_router)
app.include_router(library_router)
app.include_router(mcp_router)


@app.get("/api/health")
def health_check():
    from app.services.mcp_service import MCPClientService
    from app.database import SessionLocal
    from app.models.mistral_agent import MistralAgent

    db = SessionLocal()
    try:
        agent_count = db.query(MistralAgent).count()
    finally:
        db.close()

    from app.telemetry import is_telemetry_enabled

    return {
        "status": "ok",
        "service": "Credit Dossier API",
        "version": "2.0.0",
        "agents_initialized": agent_count,
        "orchestration_enabled": settings.ORCHESTRATION_ENABLED,
        "telemetry_enabled": is_telemetry_enabled(),
        "generation_semaphore": settings.GENERATION_SEMAPHORE,
        "orchestration_semaphore": settings.ORCHESTRATION_SEMAPHORE,
        "mcp": MCPClientService.get_health_status(),
    }

"""
FastAPI application entry point.
Mounts all routers and configures CORS for frontend integration.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup and initialize global agents."""
    logger.info("Creating database tables…")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready.")

    from app.database import SessionLocal
    from app.services.mistral_library_service import MistralLibraryService

    db = SessionLocal()
    try:
        await MistralLibraryService.initialize_global_agents(db)
    finally:
        db.close()

    yield
    logger.info("Shutting down. Cleaning up global agents...")
    
    db = SessionLocal()
    try:
        await MistralLibraryService.cleanup_global_agents(db)
    finally:
        db.close()


app = FastAPI(
    title="Credit Dossier API",
    description="Backend API for the Credit Pitch Book Pipeline — deals, narratives, exports.",
    version="1.0.0",
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


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Credit Dossier API"}

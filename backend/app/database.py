"""
PostgreSQL SQLAlchemy engine, session factory and declarative Base.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


# ── Engine configuration ────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,  # Disabled to prevent massive SQL query logs in the terminal
    pool_pre_ping=True,
)


# ── Session factory ─────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Declarative base ───────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency for FastAPI routes ───────────────────────────────
def get_db():
    """Yield a database session, close it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

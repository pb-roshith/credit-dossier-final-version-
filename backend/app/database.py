"""
SQLAlchemy engine, session factory and declarative Base.
Transparently supports SQLite (dev) and PostgreSQL (prod) based on DATABASE_URL.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


# ── Engine configuration ────────────────────────────────────────
connect_args = {}
if settings.is_sqlite:
    # SQLite needs check_same_thread=False for FastAPI's async usage
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # Disabled to prevent massive SQL query logs in the terminal
    pool_pre_ping=True,  # reconnect stale connections (useful for PostgreSQL)
)

# Enable WAL mode and foreign keys for SQLite
if settings.is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ── Session factory ─────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Declarative base ───────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency for FastAPI routes ───────────────────────────────
def get_db():
    """Yield a database session, rolling back failures and always closing it."""
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError:
        db.rollback()
        raise
    except Exception:
        # Non-database failures can still leave an open transaction behind.
        db.rollback()
        raise
    finally:
        db.close()

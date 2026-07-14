"""
Application configuration using pydantic-settings.
Supports both SQLite (local dev) and PostgreSQL (production) via DATABASE_URL.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Mistral AI ──────────────────────────────────────────────
    MISTRAL_API_KEY: str = "your_mistral_api_key_here"
    MISTRAL_MODEL: str = "mistral-large-latest"
    MISTRAL_AGENT_MODEL: str = "mistral-large-latest"

    # ── Database ────────────────────────────────────────────────
    # SQLite:      sqlite:///./credit_dossier.db
    # PostgreSQL:  postgresql://user:pass@host:5432/dbname
    DATABASE_URL: str = "sqlite:///./credit_dossier.db"

    # ── Application ─────────────────────────────────────────────
    APP_ENV: str = "development"
    UPLOAD_DIR: str = "./uploads"
    VECTOR_STORE_DIR: str = "./vector_store"

    # ── Orchestration ──────────────────────────────────────────
    ORCHESTRATION_ENABLED: bool = True

    # ── Generation ─────────────────────────────────────────────
    MAX_GROUNDING_CHARS: int = 120_000
    GENERATION_SEMAPHORE: int = 3
    ORCHESTRATION_SEMAPHORE: int = 5

    # ── MCP ────────────────────────────────────────────────────
    MCP_CACHE_TTL_SECONDS: int = 300
    MCP_CIRCUIT_BREAKER_SECONDS: int = 60
    MCP_MAX_FAILURES: int = 3
    MCP_KEEPALIVE_INTERVAL: int = 180  # seconds between keepalive pings (< Railway's 5 min timeout)

    # ── Production ─────────────────────────────────────────────
    ENABLE_TIMING_METRICS: bool = True

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def upload_path(self) -> Path:
        p = Path(self.UPLOAD_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vector_store_path(self) -> Path:
        p = Path(self.VECTOR_STORE_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()

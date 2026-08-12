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
    MISTRAL_ACCURACY_JUDGE_ID: str = ""
    MISTRAL_ACCURACY_JUDGE_MAX_SCORE: float = 100.0

    # ── Database ────────────────────────────────────────────────
    # SQLite:      sqlite:///./credit_dossier.db
    # PostgreSQL:  postgresql://user:pass@host:5432/dbname
    DATABASE_URL: str = "sqlite:///./credit_dossier.db"

    # ── Application ─────────────────────────────────────────────
    APP_ENV: str = "development"
    UPLOAD_DIR: str = "./uploads"

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
    MCP_SSE_READ_TIMEOUT: float = 300.0  # seconds — max wait for an SSE event

    # ── Production ─────────────────────────────────────────────
    ENABLE_TIMING_METRICS: bool = True

    # Initial local accounts. Override these values in backend/.env.
    INITIAL_RELATIONSHIP_MANAGER_USER_ID: str = "manager"
    INITIAL_RELATIONSHIP_MANAGER_PASSWORD: str = ""
    INITIAL_CREDIT_ANALYST_USER_ID: str = "analyst"
    INITIAL_CREDIT_ANALYST_PASSWORD: str = ""

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def upload_path(self) -> Path:
        p = Path(self.UPLOAD_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

settings = Settings()

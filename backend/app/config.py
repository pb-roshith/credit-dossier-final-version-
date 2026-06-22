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

    # ── Database ────────────────────────────────────────────────
    # SQLite:      sqlite:///./credit_dossier.db
    # PostgreSQL:  postgresql://user:pass@host:5432/dbname
    DATABASE_URL: str = "sqlite:///./credit_dossier.db"

    # ── Application ─────────────────────────────────────────────
    APP_ENV: str = "development"
    UPLOAD_DIR: str = "./uploads"
    VECTOR_STORE_DIR: str = "./vector_store"

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

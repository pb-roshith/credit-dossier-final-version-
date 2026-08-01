"""Environment-backed settings for the local credit-intelligence MCP."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


MCP_DIR = Path(__file__).resolve().parent
load_dotenv(MCP_DIR.parent / "backend" / ".env")
load_dotenv(MCP_DIR / ".env", override=True)


@dataclass(frozen=True)
class Settings:
    postgres_host: str = os.getenv("POSTGRES_HOST", "127.0.0.1")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_database: str = os.getenv("POSTGRES_DB", "credit_dossier_mcp")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "root")
    mistral_api_key: str = os.getenv("MISTRAL_API_KEY", "")
    mcp_host: str = os.getenv("MCP_HOST", "127.0.0.1")
    mcp_port: int = int(os.getenv("MCP_PORT", "8001"))
    mcp_transport: str = os.getenv("MCP_TRANSPORT", "sse")

    def postgres_kwargs(self, database: str | None = None) -> dict[str, object]:
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "dbname": database or self.postgres_database,
            "user": self.postgres_user,
            "password": self.postgres_password,
        }


settings = Settings()

"""Small, idempotent schema upgrades for existing local databases.

``Base.metadata.create_all`` creates missing tables, but it does not add newly
introduced columns to tables that already exist. These upgrades keep older
development databases usable without deleting their data.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


logger = logging.getLogger(__name__)


_ADDITIVE_MIGRATIONS: dict[str, dict[str, str]] = {
    "deals": {
        "library_sync_status": "VARCHAR(32) NOT NULL DEFAULT 'not_started'",
        "company_mistral_library_id": "VARCHAR(128)",
        "company_document_count": "INTEGER NOT NULL DEFAULT 0",
        "theme_palette": (
            """VARCHAR(256) NOT NULL DEFAULT '["#002060", "#800020"]'"""
        ),
    },
    "sections": {
        "orchestration_strategy": "TEXT",
        "original_generated_content": "TEXT",
        "final_generated_content": "TEXT",
        "moderation_status": "VARCHAR(16)",
        "moderation_details": "TEXT",
    },
    "narrative_versions": {
        "is_final": "BOOLEAN NOT NULL DEFAULT FALSE",
    },
}


def apply_additive_migrations(engine: Engine) -> list[str]:
    """Add known missing columns and return the migrations that were applied."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    applied: list[str] = []

    with engine.begin() as connection:
        for table_name, columns in _ADDITIVE_MIGRATIONS.items():
            if table_name not in existing_tables:
                continue

            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            quoted_table = engine.dialect.identifier_preparer.quote(table_name)

            for column_name, definition in columns.items():
                if column_name in existing_columns:
                    continue

                quoted_column = engine.dialect.identifier_preparer.quote(column_name)
                connection.execute(
                    text(
                        f"ALTER TABLE {quoted_table} "
                        f"ADD COLUMN {quoted_column} {definition}"
                    )
                )
                applied.append(f"{table_name}.{column_name}")

    if applied:
        logger.info("[startup] Applied database migrations: %s", ", ".join(applied))

    return applied

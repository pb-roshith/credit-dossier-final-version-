"""One-time, idempotent migration of Credit Dossier application data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, JSON, MetaData, create_engine, func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401


def _convert(value: object, column) -> object:
    if value is None:
        return None
    if isinstance(column.type, Boolean):
        return bool(value)
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(column.type, JSON) and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def migrate(sqlite_path: Path, postgres_url: str) -> dict[str, tuple[int, int]]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    source = create_engine(f"sqlite:///{sqlite_path.as_posix()}")
    destination = create_engine(postgres_url, pool_pre_ping=True)
    Base.metadata.create_all(destination)

    source_metadata = MetaData()
    source_metadata.reflect(source)
    counts: dict[str, tuple[int, int]] = {}

    with source.connect() as source_conn, destination.begin() as dest_conn:
        for target_table in Base.metadata.sorted_tables:
            source_table = source_metadata.tables.get(target_table.name)
            if source_table is None:
                continue
            source_rows = source_conn.execute(select(source_table)).mappings().all()
            if not source_rows:
                destination_count = dest_conn.scalar(
                    select(func.count()).select_from(target_table)
                )
                counts[target_table.name] = (0, int(destination_count or 0))
                continue
            rows = [
                {
                    column.name: _convert(row[column.name], column)
                    for column in target_table.columns
                    if column.name in row
                }
                for row in source_rows
            ]
            dest_conn.execute(
                postgres_insert(target_table)
                .values(rows)
                .on_conflict_do_nothing()
            )
            destination_count = dest_conn.scalar(
                select(func.count()).select_from(target_table)
            )
            counts[target_table.name] = (
                len(source_rows),
                int(destination_count or 0),
            )

    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=BACKEND_DIR / "credit_dossier.db",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("CREDIT_DOSSIER_POSTGRES_URL", ""),
    )
    args = parser.parse_args()
    if not args.postgres_url:
        raise SystemExit(
            "Set CREDIT_DOSSIER_POSTGRES_URL or pass --postgres-url."
        )
    counts = migrate(args.sqlite.resolve(), args.postgres_url)
    print("Migration complete:")
    for table, (source_count, destination_count) in counts.items():
        print(
            f"  {table}: SQLite={source_count}, PostgreSQL={destination_count}"
        )


if __name__ == "__main__":
    main()

"""Create the coach_chess database if it doesn't exist.

Uses psycopg (sync) which is the same driver Alembic uses.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg import sql

from app.core.config import get_settings

DB_NAME = "coach_chess"


def main() -> None:
    settings = get_settings()
    parsed = urlparse(settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://"))

    # Connect to the maintenance 'postgres' DB
    conninfo = (
        f"host={parsed.hostname or 'localhost'} "
        f"port={parsed.port or 5432} "
        f"user={parsed.username or 'postgres'} "
        f"dbname=postgres"
    )
    if parsed.password:
        conninfo += f" password={parsed.password}"

    with psycopg.connect(conninfo, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if cur.fetchone():
                print(f"Database '{DB_NAME}' already exists.")
                return
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
            print(f"Database '{DB_NAME}' created.")


if __name__ == "__main__":
    main()

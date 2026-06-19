"""Test fixtures.

We point at a dedicated `coach_chess_test` Postgres DB. Each test session:
  - creates all tables fresh via SQLAlchemy metadata
  - per-test: yields a session bound to a transaction that we ROLLBACK at end
  - the dev DB (`coach_chess`) is never touched
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Hard-override BEFORE app modules import settings. This protects us from
# accidentally running tests against the dev DB.
_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:root@localhost:5432/coach_chess_test",
)
os.environ["DATABASE_URL"] = _TEST_URL
os.environ["DATABASE_URL_SYNC"] = _TEST_URL.replace("+asyncpg", "+psycopg")

# Stockfish path is required even when not used directly; point to project bin
os.environ.setdefault(
    "STOCKFISH_PATH",
    "stockfish/stockfish/stockfish-windows-x86-64-avx2.exe",
)
os.environ.setdefault("CHESSCOM_USERNAME", "testuser")
# Force deterministic API key for tests, independent of dev .env
os.environ["COACH_API_KEY"] = "test-key"

from app.db.base import Base  # noqa: E402
import app.models  # noqa: F401, E402 — register all models on metadata


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _engine() -> AsyncIterator:
    engine = create_async_engine(_TEST_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(_engine) -> AsyncIterator[AsyncSession]:
    """A session whose transaction is rolled back at test end.

    SQLAlchemy "begin nested" pattern: outer connection holds the outer
    transaction; the session uses a SAVEPOINT for autocommit-like behavior.
    Easier and good enough here: just clean tables between tests.
    """
    SessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()

    # Quick cleanup: TRUNCATE all tables to start fresh next test
    from sqlalchemy import text
    async with _engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        tables = [row[0] for row in result.fetchall() if row[0] != "alembic_version"]
        if tables:
            await conn.execute(text(
                f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"
            ))

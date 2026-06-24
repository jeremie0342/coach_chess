from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.core.config import get_settings
from app.services.import_orchestrator import import_full_history, import_month
from app.services.lichess_importer import import_lichess_user

router = APIRouter(prefix="/import", tags=["imports"])


@router.post("/chesscom/full")
async def trigger_full_import(
    session: Annotated[AsyncSession, Depends(get_session)],
    username: str | None = None,
) -> dict:
    stats = await import_full_history(session, username=username)
    return {
        "imported": stats.imported,
        "updated": stats.updated,
        "skipped": stats.skipped,
        "failed": stats.failed,
        "errors": stats.errors[:20],
    }


@router.post("/lichess", summary="Import recent Lichess games of the configured user")
async def trigger_lichess_import(
    session: Annotated[AsyncSession, Depends(get_session)],
    max_games: Annotated[int, Query(ge=1, le=500)] = 100,
    username: str | None = None,
) -> dict:
    """Pulls max_games most recent Lichess games into DB. Idempotent.

    If `username` is omitted, uses LICHESS_USERNAME from .env.
    Marks them as belonging to `is_me=True` Player.
    """
    settings = get_settings()
    user = (username or settings.lichess_username or "").strip()
    if not user:
        return {"error": "LICHESS_USERNAME not configured in .env (and no username param)"}
    stats = await import_lichess_user(
        session, user, max_games=max_games, is_me=True,
    )
    return {
        "lichess_username": user,
        "imported": stats.imported,
        "skipped": stats.skipped,
        "failed": stats.failed,
        "errors": stats.errors[:10],
    }


@router.post("/chesscom/month")
async def trigger_month_import(
    session: Annotated[AsyncSession, Depends(get_session)],
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    username: str | None = None,
) -> dict:
    stats = await import_month(session, year, month, username=username)
    return {
        "year": year,
        "month": month,
        "imported": stats.imported,
        "updated": stats.updated,
        "skipped": stats.skipped,
        "failed": stats.failed,
        "errors": stats.errors[:20],
    }

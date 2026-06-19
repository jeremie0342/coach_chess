from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.import_orchestrator import import_full_history, import_month

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

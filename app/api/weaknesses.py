from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Player, Weakness
from app.services.weakness_engine import refresh_player_weaknesses

router = APIRouter(prefix="/player/me", tags=["weaknesses"])


async def _get_me(session: AsyncSession) -> Player:
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "Current player not yet imported. Run /import/chesscom/full first.")
    return me


@router.post("/weaknesses/refresh")
async def refresh(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = await _get_me(session)
    report = await refresh_player_weaknesses(session, me)
    return {
        "player": me.chesscom_username,
        "detectors_run": report.detectors_run,
        "findings": [
            {
                "category": f.category,
                "phase": f.phase,
                "occurrences": f.occurrences,
                "severity": round(f.severity, 3),
                "details": f.details,
                "sample_game_ids": f.sample_game_ids[:5],
            }
            for f in report.findings
        ],
    }


@router.get("/weaknesses")
async def list_weaknesses(
    session: Annotated[AsyncSession, Depends(get_session)],
    category: str | None = None,
    phase: str | None = None,
    min_severity: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
) -> dict:
    me = await _get_me(session)
    q = select(Weakness).where(Weakness.player_id == me.id)
    if category:
        q = q.where(Weakness.category == category)
    if phase:
        q = q.where(Weakness.phase == phase)
    q = q.where(Weakness.severity >= min_severity).order_by(Weakness.severity.desc())
    rows = list((await session.execute(q)).scalars())
    return {
        "player": me.chesscom_username,
        "count": len(rows),
        "weaknesses": [
            {
                "id": w.id,
                "category": w.category,
                "phase": w.phase,
                "occurrences": w.occurrences,
                "severity": round(w.severity, 3),
                "details": w.details,
                "sample_game_ids": (w.sample_game_ids or [])[:5],
                "updated_at": w.updated_at.isoformat(),
            }
            for w in rows
        ],
    }

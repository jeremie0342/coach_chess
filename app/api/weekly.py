from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Player, WeeklyReport
from app.services.weekly_report import generate_weekly_report

router = APIRouter(prefix="/coach/me", tags=["weekly"])


@router.get("/weekly_reports")
async def list_weekly_reports(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=52)] = 12,
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    rows = list((await session.execute(
        select(WeeklyReport)
        .where(WeeklyReport.player_id == me.id)
        .order_by(WeeklyReport.week_start.desc())
        .limit(limit)
    )).scalars())
    return {
        "count": len(rows),
        "reports": [
            {
                "id": r.id,
                "week_start": r.week_start.isoformat(),
                "week_end": r.week_end.isoformat(),
                "generated_at": r.generated_at.isoformat(),
                "games_played": r.games_played,
                "elo_delta": r.elo_delta,
                "puzzles_solved": r.puzzles_solved,
                "rep_cards_reviewed": r.rep_cards_reviewed,
                "plans_completed": r.plans_completed,
                "blunders_this_week": r.blunders_this_week,
                "weakness_deltas": r.weakness_deltas,
                "top_focus_for_next_week": r.top_focus_for_next_week,
                "narrative": r.narrative,
                "details": r.details,
            }
            for r in rows
        ],
    }


@router.post("/weekly_reports/generate")
async def trigger_weekly_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    force: bool = False,
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    r = await generate_weekly_report(session, me, force=force)
    return {
        "id": r.id,
        "week_start": r.week_start.isoformat(),
        "narrative": r.narrative,
        "elo_delta": r.elo_delta,
        "games_played": r.games_played,
    }

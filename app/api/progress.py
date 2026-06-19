from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import MetricSnapshot, Player
from app.services.auto_difficulty import recommend_next_elo
from app.services.contextual_patterns import analyse_context
from app.services.elo_calibration import calibrate
from app.services.opening_recommendation import recommend as recommend_openings
from app.services.personality import compute_personality
from app.services.progress import take_snapshot

router = APIRouter(prefix="/coach/me", tags=["progress"])


@router.get("/recommended_elo", summary="Next Stockfish ELO to play against (auto-difficulty)")
async def recommended_elo(
    session: Annotated[AsyncSession, Depends(get_session)],
    lookback: int = 10,
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    r = await recommend_next_elo(session, me, lookback=lookback)
    return {
        "next_elo": r.next_elo,
        "last_elo": r.last_elo,
        "sessions_used": r.sessions_used,
        "recent_score": r.score,
        "win_streak": r.win_streak,
        "loss_streak": r.loss_streak,
        "reason": r.reason,
    }


@router.get("/opening_recommendations", summary="Opening recommendations based on your style + record")
async def opening_recommendations(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    recs = await recommend_openings(session, me)
    return {
        "recommendations": [
            {
                "name": r.name, "eco": r.eco, "color": r.color,
                "role": r.role, "fit_score": r.fit_score,
                "short_pitch": r.short_pitch, "rationale": r.rationale,
            }
            for r in recs
        ],
    }


@router.get("/personality", summary="Your chess style vector + closest GM archetype")
async def personality(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    r = await compute_personality(session, me)
    return {
        "player": r.player,
        "moves_used": r.moves_used,
        "style": r.style.as_dict(),
        "dominant_trait": r.dominant_trait,
        "closest_gm": r.closest_gm,
        "closest_gm_similarity": r.closest_gm_similarity,
        "all_gm_matches": [{"gm": n, "similarity": s} for n, s in r.matches],
        "notes": r.notes,
    }


@router.get("/contextual_patterns", summary="When do I blunder more? Sliced views.")
async def contextual_patterns(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    r = await analyse_context(session, me)
    return {
        "baseline_blunder_rate": r.baseline_blunder_rate,
        "total_moves": r.total_moves,
        "insights": [
            {
                "metric": i.metric,
                "bucket": i.bucket,
                "blunder_rate": i.blunder_rate,
                "sample_moves": i.sample_moves,
                "relative_to_baseline": i.relative_to_baseline,
                "comment": i.comment,
            }
            for i in r.insights
        ],
    }


@router.get("/elo_calibration", summary="Estimate true ELO from sessions vs SF at known strengths")
async def elo_calibration(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    r = await calibrate(session, me)
    return {
        "player": r.player_username,
        "total_games": r.total_games,
        "estimated_elo": r.estimated_elo,
        "confidence": r.confidence,
        "reason": r.reason,
        "buckets": [
            {
                "sf_elo": b.sf_elo,
                "games": b.games,
                "wins": b.wins,
                "draws": b.draws,
                "losses": b.losses,
                "score": round(b.score, 3),
            }
            for b in r.buckets
        ],
    }


@router.post("/progress/snapshot", summary="Take a snapshot now")
async def snapshot_now(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    snap = await take_snapshot(session, me)
    return {
        "taken_at": snap.taken_at.isoformat(),
        "rating_rapid": snap.rating_rapid,
        "winrate_white": snap.winrate_white,
        "winrate_black": snap.winrate_black,
        "weakness_severities": snap.weakness_severities,
        "repertoire_due": snap.repertoire_due,
        "exercises_due": snap.exercises_due,
    }


@router.get("/progress")
async def progress_series(
    session: Annotated[AsyncSession, Depends(get_session)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = list((await session.execute(
        select(MetricSnapshot)
        .where(MetricSnapshot.player_id == me.id)
        .where(MetricSnapshot.taken_at >= since)
        .order_by(MetricSnapshot.taken_at.asc())
    )).scalars())

    return {
        "player": me.chesscom_username,
        "days": days,
        "snapshot_count": len(rows),
        "series": [
            {
                "taken_at": r.taken_at.isoformat(),
                "rating_rapid": r.rating_rapid,
                "rating_blitz": r.rating_blitz,
                "rating_bullet": r.rating_bullet,
                "winrate_white": r.winrate_white,
                "winrate_black": r.winrate_black,
                "games_total": r.games_total,
                "games_7d": r.games_7d,
                "games_30d": r.games_30d,
                "exercises_solved_total": r.exercises_solved_total,
                "exercises_solved_7d": r.exercises_solved_7d,
                "rep_cards_reviewed_7d": r.rep_cards_reviewed_7d,
                "plans_completed_7d": r.plans_completed_7d,
                "weakness_severities": r.weakness_severities,
                "repertoire_due": r.repertoire_due,
                "exercises_due": r.exercises_due,
            }
            for r in rows
        ],
    }

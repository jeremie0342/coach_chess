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
from app.services.coach.training_phase import (
    PHASE_THRESHOLDS, PHASE_TEMPLATES,
    determine_phase, phase_label,
)

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


@router.get(
    "/roadmap",
    summary="450→2000 ELO roadmap: current phase, progress toward next milestone, full phase plan",
)
async def roadmap(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")

    # Latest rating: use latest Rapid rating from games table (same logic as dashboard).
    from sqlalchemy import case, or_
    from app.models import Game
    my_rating_col = case(
        (Game.white_player_id == me.id, Game.white_rating),
        else_=Game.black_rating,
    )
    current_rating = (await session.execute(
        select(my_rating_col)
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .where(Game.time_class == "rapid")
        .where(my_rating_col.is_not(None))
        .order_by(Game.played_at.desc())
        .limit(1)
    )).scalar()

    current_phase = determine_phase(current_rating)
    rapid_30d_ago: int | None = None

    # 30-day delta from snapshots (if available)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    earliest = (await session.execute(
        select(MetricSnapshot)
        .where(MetricSnapshot.player_id == me.id)
        .where(MetricSnapshot.taken_at >= since)
        .where(MetricSnapshot.rating_rapid.is_not(None))
        .order_by(MetricSnapshot.taken_at.asc())
        .limit(1)
    )).scalar_one_or_none()
    if earliest:
        rapid_30d_ago = earliest.rating_rapid

    # Phase floors / ceilings
    floors = {"A": 0, "B": 900, "C": 1300, "D": 1700, "E": 2100}
    ceilings = {"A": 900, "B": 1300, "C": 1700, "D": 2100, "E": 3000}

    phases_out: list[dict] = []
    for letter in ["A", "B", "C", "D", "E"]:
        if letter < current_phase:
            state = "done"
        elif letter == current_phase:
            state = "current"
        else:
            state = "upcoming"
        template = PHASE_TEMPLATES.get(letter, [])
        phases_out.append({
            "letter": letter,
            "label": phase_label(letter),
            "floor": floors[letter],
            "ceiling": ceilings[letter],
            "state": state,
            "items": [
                {
                    "kind": str(s.kind),
                    "title": s.title,
                    "target_count": s.target_count,
                    "minutes": s.minutes,
                    "rationale": s.rationale,
                }
                for s in template
            ],
        })

    # Progress toward next milestone (current phase ceiling, capped at 2000 for goal)
    GOAL = 2000
    floor = floors[current_phase]
    ceiling = ceilings[current_phase]
    next_milestone = ceiling if ceiling <= GOAL else GOAL

    progress_in_phase = None
    if current_rating is not None:
        span = max(1, next_milestone - floor)
        progress_in_phase = max(0.0, min(1.0, (current_rating - floor) / span))

    # Estimate days to next milestone from 30d ELO velocity (very rough)
    eta_days = None
    if current_rating is not None and rapid_30d_ago is not None and current_rating > rapid_30d_ago:
        velocity_per_day = (current_rating - rapid_30d_ago) / 30
        remaining = next_milestone - current_rating
        if remaining > 0 and velocity_per_day > 0:
            eta_days = int(remaining / velocity_per_day)

    return {
        "goal_rating": GOAL,
        "current_rating": current_rating,
        "current_phase": current_phase,
        "rapid_30d_ago": rapid_30d_ago,
        "rating_delta_30d": (current_rating - rapid_30d_ago)
            if current_rating is not None and rapid_30d_ago is not None else None,
        "next_milestone": next_milestone,
        "progress_in_phase": round(progress_in_phase, 3) if progress_in_phase is not None else None,
        "eta_days_to_next_milestone": eta_days,
        "phases": phases_out,
        "thresholds": [{"rating": t, "next_phase": p} for t, p in PHASE_THRESHOLDS],
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

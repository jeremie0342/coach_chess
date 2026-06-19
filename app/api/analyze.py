from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Game
from app.services.analyzer import analyze_game
from app.services.deep_analyzer import deep_analyze_critical
from app.services.stockfish import get_engine

router = APIRouter(tags=["analysis"])


@router.post("/games/{game_id}/analyze")
async def analyze_one(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    depth: Annotated[int | None, Query(ge=8, le=40)] = None,
    force: bool = False,
) -> dict:
    game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")
    engine = await get_engine()
    stats = await analyze_game(session, game, engine, depth=depth, force=force)
    return {
        "game_id": stats.game_id,
        "moves_analyzed": stats.moves_analyzed,
        "blunders": stats.blunders,
        "mistakes": stats.mistakes,
        "inaccuracies": stats.inaccuracies,
        "elapsed_s": round(stats.elapsed_s, 2),
    }


@router.post("/analyze/pending")
async def analyze_pending(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    depth: Annotated[int | None, Query(ge=8, le=40)] = None,
) -> dict:
    q = (
        select(Game)
        .where(Game.analysis_status == "pending")
        .order_by(Game.played_at.desc())
        .limit(limit)
    )
    games = list((await session.execute(q)).scalars())
    engine = await get_engine()
    total = {"games": 0, "moves": 0, "blunders": 0, "mistakes": 0, "inaccuracies": 0, "elapsed_s": 0.0}
    for g in games:
        s = await analyze_game(session, g, engine, depth=depth)
        total["games"] += 1
        total["moves"] += s.moves_analyzed
        total["blunders"] += s.blunders
        total["mistakes"] += s.mistakes
        total["inaccuracies"] += s.inaccuracies
        total["elapsed_s"] += s.elapsed_s
    total["elapsed_s"] = round(total["elapsed_s"], 2)
    return total


@router.post(
    "/analyze/deep/critical",
    summary="Re-analyze player's worst N blunders at high depth",
)
async def deep_critical(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
    depth: Annotated[int, Query(ge=18, le=40)] = 28,
    min_cp_loss: Annotated[int, Query(ge=50)] = 150,
    force: bool = False,
) -> dict:
    stats = await deep_analyze_critical(
        session, limit=limit, depth=depth,
        min_cp_loss=min_cp_loss, force=force,
    )
    return {
        "moves_deep_analyzed": stats.moves_deep_analyzed,
        "skipped_existing": stats.skipped_existing,
        "elapsed_s": round(stats.elapsed_s, 1),
    }

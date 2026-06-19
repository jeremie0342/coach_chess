from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Exercise, Player
from app.models.exercise import ExerciseKind
from app.services.exercises.generator import generate_for_player
from app.services.exercises.solver import (
    compute_stats,
    grade_answer,
    pick_next_due,
)

router = APIRouter(prefix="/exercises", tags=["exercises"])


class SolveIn(BaseModel):
    exercise_id: int
    move: str           # SAN or UCI
    time_ms: int | None = None


@router.post("/generate")
async def generate(
    session: Annotated[AsyncSession, Depends(get_session)],
    min_cp_loss: int = 120,
) -> dict:
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    stats = await generate_for_player(session, me, min_cp_loss=min_cp_loss)
    return {
        "inserted": stats.inserted,
        "skipped_existing": stats.skipped_existing,
        "skipped_no_best": stats.skipped_no_best,
        "failed": stats.failed,
    }


@router.get("/next")
async def next_exercise(
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: ExerciseKind | None = None,
    theme: str | None = None,
    source_kind: str | None = None,
    rating: int | None = None,
    rating_window: int = 150,
) -> dict:
    nxt = await pick_next_due(
        session, kind=kind, theme=theme,
        source_kind=source_kind, rating=rating, rating_window=rating_window,
    )
    if not nxt:
        return {"has_exercise": False}
    ex = nxt.exercise
    return {
        "has_exercise": True,
        "is_new": nxt.is_new,
        "due_now": nxt.due_now,
        "exercise": {
            "id": ex.id,
            "title": ex.title,
            "fen": ex.fen,
            "side_to_move": ex.side_to_move,
            "kind": str(ex.kind),
            "difficulty": ex.difficulty,
            "themes": ex.theme_tags,
            "source_game_id": ex.source_game_id,
        },
    }


@router.post("/answer")
async def answer(
    payload: SolveIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    ex = (await session.execute(
        select(Exercise).where(Exercise.id == payload.exercise_id)
    )).scalar_one_or_none()
    if not ex:
        raise HTTPException(404, "exercise not found")
    r = await grade_answer(session, ex, payload.move, time_ms=payload.time_ms)
    return {
        "exercise_id": r.exercise_id,
        "correct": r.correct,
        "grade": r.grade,
        "user_uci": r.user_uci,
        "expected_uci": r.expected_uci,
        "expected_san": r.expected_san,
        "new_interval_days": r.new_interval_days,
        "new_due_at": r.new_due_at.isoformat(),
    }


@router.get("/stats")
async def stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: ExerciseKind | None = None,
) -> dict:
    s = await compute_stats(session, kind=kind)
    return {
        "total": s.total,
        "new": s.new,
        "learning": s.learning,
        "due_today": s.due_today,
        "next_due_at": s.next_due_at.isoformat() if s.next_due_at else None,
    }

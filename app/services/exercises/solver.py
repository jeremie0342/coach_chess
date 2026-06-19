"""Pick the next exercise to solve and grade an answer.

Grading rules (move comparison):
  - User's first move equals solution[0]            -> q=5 (or 4 if slow)
  - User plays a different move but it's also a top
    Stockfish line (cp_loss ~0)                    -> q=4 (only if we cheaply know)
  - User's move would lose material immediately    -> q=0
  - Otherwise                                      -> q=1

For now we don't re-run Stockfish at solve-time (too slow). We treat
solution[0] as canonical and grade strictly on exact match. The training
loop still works thanks to SR.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import chess
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Exercise
from app.models.exercise import ExerciseKind
from app.services.trainer.srs import SRState, grade as sm2_grade


@dataclass
class NextExercise:
    exercise: Exercise
    is_new: bool
    due_now: bool


@dataclass
class ExerciseStats:
    total: int
    new: int
    learning: int
    due_today: int
    next_due_at: datetime | None


def _state_from(ex: Exercise) -> SRState:
    return SRState(
        ease=ex.sr_ease,
        interval_days=ex.sr_interval_days,
        repetitions=ex.sr_repetitions,
        due_at=ex.sr_due_at,
        last_reviewed_at=ex.sr_last_reviewed_at,
    )


async def pick_next_due(
    session: AsyncSession,
    kind: ExerciseKind | None = None,
    theme: str | None = None,
    source_kind: str | None = None,
    rating: int | None = None,
    rating_window: int = 150,
) -> NextExercise | None:
    """Pick the next puzzle to serve.

    Filters:
      - kind          : tactic / endgame / opening / ...
      - theme         : a specific tag in theme_tags (e.g. 'fork', 'missed_win')
      - source_kind   : 'blunder' (from my own games), 'lichess', 'manual'
      - rating        : player's current ELO; puzzles within +/- rating_window
                        are prioritized (use difficulty as proxy for puzzle rating)
    """
    from sqlalchemy import func
    now = datetime.now(timezone.utc)
    base = select(Exercise)
    if kind is not None:
        base = base.where(Exercise.kind == kind)
    if theme is not None:
        base = base.where(Exercise.theme_tags.op("?")(theme))
    if source_kind is not None:
        base = base.where(Exercise.source_kind == source_kind)
    if rating is not None:
        base = base.where(
            Exercise.difficulty >= rating - rating_window,
            Exercise.difficulty <= rating + rating_window,
        )

    # 1. cards already in review and due
    due_q = (
        base.where(
            Exercise.sr_due_at.is_not(None),
            Exercise.sr_due_at <= now,
            Exercise.sr_repetitions > 0,
        )
        .order_by(Exercise.sr_due_at.asc())
        .limit(1)
    )
    due_ex = (await session.execute(due_q)).scalar_one_or_none()
    if due_ex:
        return NextExercise(exercise=due_ex, is_new=False, due_now=True)

    # 2. brand-new. Order strategy depends on what's available:
    #    - if rating filter is on: pick closest to rating, then most popular
    #    - else: easiest first (low-difficulty blunders are confidence-builders)
    if rating is not None:
        rating_distance = func.abs(Exercise.difficulty - rating)
        new_q = (
            base.where(Exercise.sr_repetitions == 0)
            .order_by(rating_distance.asc(), Exercise.popularity.desc().nullslast())
            .limit(1)
        )
    else:
        new_q = (
            base.where(Exercise.sr_repetitions == 0)
            .order_by(Exercise.difficulty.asc())
            .limit(1)
        )
    new_ex = (await session.execute(new_q)).scalar_one_or_none()
    if new_ex:
        return NextExercise(exercise=new_ex, is_new=True, due_now=False)
    return None


@dataclass
class GradedExercise:
    exercise_id: int
    correct: bool
    grade: int
    user_uci: str | None
    expected_uci: str
    expected_san: str
    new_interval_days: int
    new_due_at: datetime


async def grade_answer(
    session: AsyncSession,
    exercise: Exercise,
    user_input: str,
    time_ms: int | None = None,
) -> GradedExercise:
    board = chess.Board(exercise.fen)
    expected_uci = exercise.solution_uci[0] if exercise.solution_uci else ""
    expected_san = ""
    if expected_uci:
        try:
            expected_san = board.san(chess.Move.from_uci(expected_uci))
        except Exception:
            expected_san = expected_uci

    user_move: chess.Move | None = None
    try:
        user_move = board.parse_san(user_input.strip())
    except (ValueError, chess.InvalidMoveError):
        try:
            user_move = chess.Move.from_uci(user_input.strip())
            if user_move not in board.legal_moves:
                user_move = None
        except (ValueError, chess.InvalidMoveError):
            user_move = None

    user_uci = user_move.uci() if user_move else None
    correct = bool(user_move) and (user_uci == expected_uci)

    if correct:
        q = 5 if (time_ms is not None and time_ms < 8000) else 4
    elif user_move is None:
        q = 0
    else:
        q = 1

    state = _state_from(exercise)
    result = sm2_grade(state, q)
    exercise.sr_ease = result.new.ease
    exercise.sr_interval_days = result.new.interval_days
    exercise.sr_repetitions = result.new.repetitions
    exercise.sr_due_at = result.new.due_at
    exercise.sr_last_reviewed_at = result.new.last_reviewed_at
    exercise.attempts = (exercise.attempts or 0) + 1
    if correct:
        exercise.successes = (exercise.successes or 0) + 1

    await session.commit()
    return GradedExercise(
        exercise_id=exercise.id,
        correct=correct,
        grade=q,
        user_uci=user_uci,
        expected_uci=expected_uci,
        expected_san=expected_san,
        new_interval_days=result.new.interval_days,
        new_due_at=result.new.due_at,
    )


async def compute_stats(
    session: AsyncSession, kind: ExerciseKind | None = None
) -> ExerciseStats:
    now = datetime.now(timezone.utc)
    base = select(Exercise)
    if kind is not None:
        base = base.where(Exercise.kind == kind)

    total = (await session.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    new = (await session.execute(
        select(func.count()).select_from(
            base.where(Exercise.sr_repetitions == 0).subquery()
        )
    )).scalar_one()
    learning = (await session.execute(
        select(func.count()).select_from(
            base.where(Exercise.sr_repetitions > 0).subquery()
        )
    )).scalar_one()
    due = (await session.execute(
        select(func.count()).select_from(
            base.where(Exercise.sr_due_at.is_not(None), Exercise.sr_due_at <= now).subquery()
        )
    )).scalar_one()
    next_due = (await session.execute(
        select(func.min(Exercise.sr_due_at)).where(Exercise.sr_due_at.is_not(None))
    )).scalar()
    return ExerciseStats(
        total=total, new=new, learning=learning,
        due_today=due, next_due_at=next_due,
    )

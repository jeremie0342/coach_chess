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
    themes: list[str] | None = None,
    exclude_themes: list[str] | None = None,
    source_kind: str | None = None,
    rating: int | None = None,
    rating_window: int = 150,
) -> NextExercise | None:
    """Pick the next puzzle to serve.

    Filters:
      - kind            : tactic / endgame / opening / ...
      - theme           : single tag (legacy)
      - themes          : list of tags, OR semantics (any-of)
      - exclude_themes  : list of tags to ban (none-of). Useful to filter out
                          "mate"/"mateInN" tags when user wants a pure motif.
      - source_kind     : 'blunder' (from my own games), 'lichess', 'manual'
      - rating          : player's current ELO; puzzles within +/- rating_window
                          are prioritized
    """
    from sqlalchemy import and_, func, not_, or_
    now = datetime.now(timezone.utc)
    base = select(Exercise)
    if kind is not None:
        base = base.where(Exercise.kind == kind)
    # Merge legacy `theme` into `themes` so both work in tandem
    want_themes = list(themes or [])
    if theme:
        want_themes.append(theme)
    if want_themes:
        # OR semantics via OR-of single `?` ops (each is JSONB key-exists)
        base = base.where(or_(*[Exercise.theme_tags.op("?")(t) for t in want_themes]))
    if exclude_themes:
        # NOT any-of -> AND of NOTs
        base = base.where(and_(*[not_(Exercise.theme_tags.op("?")(t)) for t in exclude_themes]))
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
    complete: bool
    grade: int
    step: int
    user_uci: str | None
    expected_uci: str
    expected_san: str
    opponent_uci: str | None
    opponent_san: str | None
    fen_after_opponent: str | None
    next_expected_uci: str | None
    next_expected_san: str | None
    new_interval_days: int
    new_due_at: datetime


def _apply_until_step(board: chess.Board, solution_uci: list[str], step: int) -> None:
    """Apply trigger + previous (user, opp) pairs so the board matches the
    position the user is facing for `step`."""
    upto = min(2 * step + 1, len(solution_uci))
    for u in solution_uci[:upto]:
        try:
            mv = chess.Move.from_uci(u)
            if mv in board.legal_moves:
                board.push(mv)
        except (ValueError, chess.InvalidMoveError):
            return


async def grade_answer(
    session: AsyncSession,
    exercise: Exercise,
    user_input: str,
    time_ms: int | None = None,
    step: int = 0,
) -> GradedExercise:
    solution = list(exercise.solution_uci or [])
    n_user_steps = max(1, len(solution) // 2)
    step = max(0, min(step, n_user_steps - 1))

    # Index of expected user move in raw solution list (skip trigger at 0).
    user_idx = 2 * step + 1
    expected_uci = solution[user_idx] if user_idx < len(solution) else ""

    # Reconstruct the position the user is facing right now.
    board = chess.Board(exercise.fen)
    _apply_until_step(board, solution, step)

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

    is_last_user_step = (step == n_user_steps - 1)
    complete = correct and is_last_user_step

    opp_uci: str | None = None
    opp_san: str | None = None
    fen_after_opp: str | None = None
    next_expected_uci: str | None = None
    next_expected_san: str | None = None

    if correct and not is_last_user_step:
        board.push(user_move)  # type: ignore[arg-type]
        opp_idx = 2 * step + 2
        if opp_idx < len(solution):
            opp_uci = solution[opp_idx]
            try:
                mv_opp = chess.Move.from_uci(opp_uci)
                if mv_opp in board.legal_moves:
                    opp_san = board.san(mv_opp)
                    board.push(mv_opp)
            except Exception:
                pass
        fen_after_opp = board.fen()
        next_idx = 2 * (step + 1) + 1
        if next_idx < len(solution):
            next_expected_uci = solution[next_idx]
            try:
                next_expected_san = board.san(chess.Move.from_uci(next_expected_uci))
            except Exception:
                next_expected_san = next_expected_uci

    # SM-2 only on terminal outcome (failure OR full completion).
    terminal = (not correct) or complete
    if terminal:
        if complete:
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
        if complete:
            exercise.successes = (exercise.successes or 0) + 1
            exercise.last_solved_at = datetime.now(timezone.utc)
        new_interval = result.new.interval_days
        new_due = result.new.due_at
    else:
        q = 4
        new_interval = exercise.sr_interval_days or 0
        new_due = exercise.sr_due_at or datetime.now(timezone.utc)

    await session.commit()
    return GradedExercise(
        exercise_id=exercise.id,
        correct=correct,
        complete=complete,
        grade=q,
        step=step,
        user_uci=user_uci,
        expected_uci=expected_uci,
        expected_san=expected_san,
        opponent_uci=opp_uci,
        opponent_san=opp_san,
        fen_after_opponent=fen_after_opp,
        next_expected_uci=next_expected_uci,
        next_expected_san=next_expected_san,
        new_interval_days=new_interval,
        new_due_at=new_due,
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

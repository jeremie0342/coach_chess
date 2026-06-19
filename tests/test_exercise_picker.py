"""Exercise picker filters: source_kind, theme, rating window."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Exercise
from app.models.exercise import ExerciseKind, ExerciseSource
from app.services.exercises.solver import pick_next_due
from tests.factories import make_player


pytestmark = pytest.mark.db


def _ex(
    fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    solution: list[str] | None = None,
    *,
    source_kind: str = "lichess",
    difficulty: int = 1500,
    themes: list[str] | None = None,
    lichess_id: str | None = None,
) -> Exercise:
    return Exercise(
        source_kind=source_kind,
        lichess_id=lichess_id,
        kind=ExerciseKind.TACTIC,
        fen=fen,
        side_to_move="w",
        solution_uci=solution or ["e2e4"],
        difficulty=difficulty,
        theme_tags=themes or ["middlegame"],
        sr_due_at=None,
    )


async def test_filter_by_rating_window(db_session) -> None:
    await make_player(db_session, "alice")
    db_session.add_all([
        _ex(difficulty=400, themes=["fork"], lichess_id="A"),
        _ex(difficulty=600, themes=["fork"], lichess_id="B"),
        _ex(difficulty=2000, themes=["fork"], lichess_id="C"),
    ])
    await db_session.commit()
    nxt = await pick_next_due(db_session, rating=500, rating_window=150)
    assert nxt is not None
    # difficulty must be within [350, 650] — A (400) or B (600)
    assert nxt.exercise.difficulty in (400, 600)


async def test_filter_by_theme(db_session) -> None:
    await make_player(db_session, "alice")
    db_session.add_all([
        _ex(difficulty=500, themes=["fork"], lichess_id="A"),
        _ex(difficulty=500, themes=["mateIn1"], lichess_id="B"),
    ])
    await db_session.commit()
    nxt = await pick_next_due(db_session, theme="mateIn1")
    assert nxt is not None
    assert "mateIn1" in (nxt.exercise.theme_tags or [])


async def test_filter_by_source_kind(db_session) -> None:
    await make_player(db_session, "alice")
    db_session.add_all([
        _ex(source_kind="blunder", difficulty=500, lichess_id=None),
        _ex(source_kind="lichess", difficulty=500, lichess_id="A"),
    ])
    await db_session.commit()
    nxt = await pick_next_due(db_session, source_kind="blunder")
    assert nxt is not None
    assert str(nxt.exercise.source_kind) == "ExerciseSource.BLUNDER" or nxt.exercise.source_kind == ExerciseSource.BLUNDER


async def test_due_card_returns_before_new_card(db_session) -> None:
    """A card already in review (sr_repetitions > 0) and due-now beats a brand-new one."""
    await make_player(db_session, "alice")
    now = datetime.now(timezone.utc)
    e_new = _ex(difficulty=300, lichess_id="N")        # new (sr_repetitions=0)
    e_due = _ex(difficulty=2000, lichess_id="D")
    e_due.sr_repetitions = 2
    e_due.sr_due_at = now - timedelta(days=1)
    db_session.add_all([e_new, e_due])
    await db_session.commit()
    nxt = await pick_next_due(db_session)
    assert nxt is not None
    assert nxt.is_new is False
    assert nxt.exercise.lichess_id == "D"


async def test_returns_none_when_pool_empty(db_session) -> None:
    nxt = await pick_next_due(db_session, theme="nonexistent_theme_xyz")
    assert nxt is None

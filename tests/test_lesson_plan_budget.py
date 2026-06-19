"""Lesson plan budget-fitting algorithm."""
from __future__ import annotations

from app.models.daily_plan import DailyItemKind
from app.services.coach.lesson_plan import _Candidate, _fit_to_budget


def _candidate(kind: DailyItemKind, count: int, prio: float) -> _Candidate:
    return _Candidate(
        kind=kind,
        title=f"{kind.value}-{count}",
        target_count=count,
        filters={},
        rationale="",
        priority=prio,
    )


def test_empty_input_returns_empty() -> None:
    assert _fit_to_budget([], target_minutes=30) == []


def test_priority_sorting_is_descending() -> None:
    candidates = [
        _candidate(DailyItemKind.PUZZLE_FOCUSED, 5, prio=0.3),
        _candidate(DailyItemKind.PUZZLE_FOCUSED, 5, prio=0.9),
        _candidate(DailyItemKind.PUZZLE_FOCUSED, 5, prio=0.6),
    ]
    picked = _fit_to_budget(candidates, target_minutes=60)
    assert [c.priority for c in picked] == [0.9, 0.6, 0.3]


def test_budget_caps_total_minutes() -> None:
    # Each puzzle costs 1.0 min. 30 min budget, 50 puzzles requested -> trims.
    c = _candidate(DailyItemKind.PUZZLE_FOCUSED, 50, prio=1.0)
    picked = _fit_to_budget([c], target_minutes=30)
    assert len(picked) == 1
    assert picked[0].target_count == 30


def test_low_priority_items_dropped_when_full() -> None:
    candidates = [
        _candidate(DailyItemKind.PUZZLE_FOCUSED, 30, prio=1.0),  # fills budget
        _candidate(DailyItemKind.PUZZLE_FOCUSED, 10, prio=0.1),  # should be dropped
    ]
    picked = _fit_to_budget(candidates, target_minutes=30)
    assert len(picked) == 1
    assert picked[0].priority == 1.0


def test_coach_note_always_included_regardless_of_budget() -> None:
    note = _candidate(DailyItemKind.COACH_NOTE, 0, prio=0.05)
    picked = _fit_to_budget([note], target_minutes=0)
    assert len(picked) == 1
    assert picked[0].kind == DailyItemKind.COACH_NOTE


def test_repertoire_cheaper_than_puzzles() -> None:
    """At 0.3 min/card vs 1.0 min/puzzle, repertoire fits more in same budget."""
    rep = _candidate(DailyItemKind.REPERTOIRE_DRILL, 100, prio=1.0)
    picked = _fit_to_budget([rep], target_minutes=30)
    assert picked[0].target_count == 100   # 100 * 0.3 = 30 min — exact fit

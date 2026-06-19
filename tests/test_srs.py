"""SM-2 scheduler invariants."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.trainer.srs import MIN_EASE, SRState, grade, initial_state


def _fresh() -> SRState:
    return initial_state()


def test_initial_state_defaults() -> None:
    s = initial_state()
    assert s.ease == 2.5
    assert s.interval_days == 0
    assert s.repetitions == 0
    assert s.due_at is None


def test_failure_resets_repetitions_and_keeps_min_ease() -> None:
    s = _fresh()
    s.repetitions = 3
    s.ease = 1.4
    s.interval_days = 21
    r = grade(s, q=0)
    assert r.success is False
    assert r.new.repetitions == 0
    assert r.new.interval_days == 1
    assert r.new.ease >= MIN_EASE


def test_first_success_schedules_one_day() -> None:
    r = grade(_fresh(), q=4)
    assert r.success
    assert r.new.repetitions == 1
    assert r.new.interval_days == 1


def test_second_success_schedules_six_days() -> None:
    s = _fresh()
    s = grade(s, q=4).new
    r = grade(s, q=4)
    assert r.new.repetitions == 2
    assert r.new.interval_days == 6


def test_third_success_uses_ease_multiplier() -> None:
    s = _fresh()
    s = grade(s, q=5).new
    s = grade(s, q=5).new   # 6 days, rep=2
    s = grade(s, q=5).new   # interval * ease
    assert s.repetitions == 3
    # 6 * (>=2.5 since q=5 bumps ease) >= 15
    assert s.interval_days >= 15


def test_quality_5_increases_ease() -> None:
    s = _fresh()
    r = grade(s, q=5)
    assert r.new.ease > 2.5  # quality 5 should bump ease


def test_quality_3_keeps_ease_near_baseline() -> None:
    s = _fresh()
    r = grade(s, q=3)
    # q=3: delta = 0.1 - 2*(0.08 + 2*0.02) = 0.1 - 0.24 = -0.14
    assert 2.3 < r.new.ease < 2.5


def test_ease_floor_at_1_3() -> None:
    s = _fresh()
    s.ease = 1.4
    # bombard with failures
    for _ in range(20):
        s = grade(s, q=0).new
    assert s.ease == pytest.approx(MIN_EASE)


def test_due_at_offset_matches_interval() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s = _fresh()
    r = grade(s, q=5, now=now)
    assert r.new.due_at == now + timedelta(days=r.new.interval_days)
    assert r.new.last_reviewed_at == now

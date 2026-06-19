"""SM-2 spaced repetition scheduler (the same family used by Anki).

State per card:
    ease         : float, starts at 2.5, never below 1.3
    interval     : days until next review
    repetitions  : count of consecutive successful reviews
    due_at       : when the card is next due

Grade scale 0..5 (we accept these via the trainer):
    0  : total blackout (didn't know at all)
    1  : wrong but recognised the position
    2  : wrong, but with hesitation indicating partial recall
    3  : correct, with significant effort
    4  : correct, with hesitation
    5  : perfect recall, fast

Algorithm:
    - q < 3  -> failure: repetitions = 0, interval = 1 day
    - q >= 3 -> success: repetitions += 1, schedule:
                 r==1 : 1 day
                 r==2 : 6 days
                 else : interval * ease
    - Ease update (any q):
        ease' = max(1.3, ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


MIN_EASE = 1.3
DEFAULT_EASE = 2.5


@dataclass
class SRState:
    ease: float
    interval_days: int
    repetitions: int
    due_at: datetime | None
    last_reviewed_at: datetime | None


@dataclass
class GradeResult:
    new: SRState
    grade: int
    success: bool


def grade(state: SRState, q: int, now: datetime | None = None) -> GradeResult:
    """Apply SM-2 to `state` given quality `q` in 0..5. Returns new state."""
    q = max(0, min(5, int(q)))
    now = now or datetime.now(timezone.utc)
    success = q >= 3

    if not success:
        repetitions = 0
        interval = 1
    else:
        repetitions = state.repetitions + 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 6
        else:
            interval = max(1, int(round(state.interval_days * state.ease)))

    ease = max(MIN_EASE, state.ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    new = SRState(
        ease=ease,
        interval_days=interval,
        repetitions=repetitions,
        due_at=now + timedelta(days=interval),
        last_reviewed_at=now,
    )
    return GradeResult(new=new, grade=q, success=success)


def initial_state() -> SRState:
    return SRState(
        ease=DEFAULT_EASE,
        interval_days=0,
        repetitions=0,
        due_at=None,
        last_reviewed_at=None,
    )

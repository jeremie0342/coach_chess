"""Estimate the user's true ELO from past position_sessions against
Stockfish at known strengths.

We bucket finished sessions by sf_elo (rounded to the nearest 100), compute
the user's win+½draw score in each bucket, and estimate true ELO by linear
interpolation around the level where the score crosses 50%.

Inspired by the standard ELO performance formula: a user scoring 50% vs
SF Elo X is roughly Elo X themselves. Below 50% they're weaker; above,
they're stronger.

The estimator is intentionally simple — it's a personal coach signal, not a
FIDE rating.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player, PositionSession
from app.models.position_session import PositionSessionStatus

logger = logging.getLogger(__name__)


@dataclass
class EloBucket:
    sf_elo: int
    games: int
    wins: int
    draws: int
    losses: int

    @property
    def score(self) -> float:
        return (self.wins + 0.5 * self.draws) / max(self.games, 1)


@dataclass
class CalibrationReport:
    player_username: str | None
    total_games: int
    buckets: list[EloBucket] = field(default_factory=list)
    estimated_elo: int | None = None
    confidence: str = "low"
    reason: str = ""


def _round_elo(elo: int | None) -> int | None:
    if elo is None:
        return None
    return int(round(elo / 100.0)) * 100


def _classify_result(sess: PositionSession) -> str:
    s = sess.status
    if s == PositionSessionStatus.USER_WON:
        return "win"
    if s == PositionSessionStatus.DRAW:
        return "draw"
    if s == PositionSessionStatus.USER_LOST:
        return "loss"
    return "skip"   # active or abandoned


def _interpolate_elo(buckets: list[EloBucket]) -> tuple[int | None, str]:
    """Find the ELO level where score crosses 50%.

    If user is below 50% everywhere → estimate = lowest_bucket_elo - delta
    If above 50% everywhere → highest + delta
    Otherwise → linear interpolation.
    """
    ordered = sorted(buckets, key=lambda b: b.sf_elo)
    if not ordered:
        return None, "no games"

    scores = [b.score for b in ordered]
    if all(s >= 0.5 for s in scores):
        return ordered[-1].sf_elo + 100, "above all levels (estimate is a floor)"
    if all(s < 0.5 for s in scores):
        return max(0, ordered[0].sf_elo - 100), "below all levels (estimate is a ceiling)"

    # Find the bracket where we cross 50%
    for a, b in zip(ordered, ordered[1:]):
        if a.score >= 0.5 and b.score < 0.5:
            high, low = a, b
        elif a.score < 0.5 and b.score >= 0.5:
            low, high = a, b
        else:
            continue
        denom = (high.score - low.score)
        if abs(denom) < 1e-6:
            return (high.sf_elo + low.sf_elo) // 2, "flat curve"
        t = (0.5 - low.score) / denom
        elo = low.sf_elo + t * (high.sf_elo - low.sf_elo)
        return int(round(elo / 25) * 25), "interpolated"
    return None, "could not bracket 50%"


def _confidence_label(total_games: int, buckets_used: int) -> str:
    if total_games >= 30 and buckets_used >= 3:
        return "high"
    if total_games >= 12 and buckets_used >= 2:
        return "medium"
    return "low"


async def calibrate(session: AsyncSession, player: Player) -> CalibrationReport:
    rows = list((await session.execute(
        select(PositionSession)
        .where(PositionSession.player_id == player.id)
        .where(PositionSession.sf_elo.is_not(None))
        .where(PositionSession.status.in_((
            PositionSessionStatus.USER_WON,
            PositionSessionStatus.DRAW,
            PositionSessionStatus.USER_LOST,
        )))
    )).scalars())

    by_elo: dict[int, EloBucket] = {}
    for sess in rows:
        e = _round_elo(sess.sf_elo)
        if e is None:
            continue
        b = by_elo.setdefault(e, EloBucket(sf_elo=e, games=0, wins=0, draws=0, losses=0))
        b.games += 1
        r = _classify_result(sess)
        if r == "win":
            b.wins += 1
        elif r == "draw":
            b.draws += 1
        elif r == "loss":
            b.losses += 1

    buckets = sorted(by_elo.values(), key=lambda b: b.sf_elo)
    elo, reason = _interpolate_elo(buckets) if buckets else (None, "no games")
    return CalibrationReport(
        player_username=player.chesscom_username,
        total_games=sum(b.games for b in buckets),
        buckets=buckets,
        estimated_elo=elo,
        confidence=_confidence_label(sum(b.games for b in buckets), len(buckets)),
        reason=reason,
    )

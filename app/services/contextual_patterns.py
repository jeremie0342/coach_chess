"""Detect contextual blunder patterns: when do I blunder more?

We slice the player's blunder rate by:
  - opponent rating delta (much weaker / similar / much stronger)
  - phase of game (opening / middlegame / endgame)
  - time pressure (clock_seconds remaining when move was played)
  - day-of-week and hour-of-day (chronotype effects)

Returns a list of insights with relative magnitude — "you blunder 2.3x more
in time-trouble than otherwise."

Pure SQL; no extra Stockfish work needed since blunders are already
classified in MoveAnalysis.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import and_, case, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, MoveAnalysis, Player
from app.models.analysis import MoveQuality

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    metric: str
    bucket: str
    blunder_rate: float
    sample_moves: int
    relative_to_baseline: float    # how many ×  the baseline rate
    comment: str


@dataclass
class ContextReport:
    baseline_blunder_rate: float
    total_moves: int
    insights: list[Insight] = field(default_factory=list)


BLUNDER_QUALITIES = (MoveQuality.BLUNDER, MoveQuality.MISTAKE)


async def _baseline(session: AsyncSession, player: Player) -> tuple[int, int]:
    """Return (n_blunders, n_moves) for ME across all analyzed moves."""
    my_is_white = case(
        (Game.white_player_id == player.id, True),
        else_=False,
    )
    n_total = (await session.execute(
        select(func.count(Move.id))
        .join(Game, Game.id == Move.game_id)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Move.is_white == my_is_white)
    )).scalar_one()
    n_blunders = (await session.execute(
        select(func.count(Move.id))
        .join(Game, Game.id == Move.game_id)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Move.is_white == my_is_white)
        .where(MoveAnalysis.quality.in_(BLUNDER_QUALITIES))
    )).scalar_one()
    return n_blunders, n_total


def _rel(rate: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return rate / baseline


def _comment(metric: str, bucket: str, rel: float) -> str:
    if rel >= 1.5:
        return f"{metric}={bucket}: {rel:.1f}× plus de blunders que la moyenne"
    if rel <= 0.7:
        return f"{metric}={bucket}: {rel:.1f}× — tu blunders MOINS dans ce contexte"
    return ""


async def _opponent_rating_delta(
    session: AsyncSession, player: Player, baseline: float
) -> list[Insight]:
    my_is_white = case(
        (Game.white_player_id == player.id, True),
        else_=False,
    )
    my_rating = case(
        (Game.white_player_id == player.id, Game.white_rating),
        else_=Game.black_rating,
    )
    opp_rating = case(
        (Game.white_player_id == player.id, Game.black_rating),
        else_=Game.white_rating,
    )
    delta = (opp_rating - my_rating).label("delta")
    bucket = case(
        (delta <= -100, "much_weaker"),
        (delta <= -25, "weaker"),
        (delta >= 100, "much_stronger"),
        (delta >= 25, "stronger"),
        else_="similar",
    ).label("bucket")
    rows = (await session.execute(
        select(
            bucket,
            func.count(Move.id).label("n"),
            func.sum(case((MoveAnalysis.quality.in_(BLUNDER_QUALITIES), 1), else_=0)).label("bl"),
        )
        .join(Game, Game.id == Move.game_id)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Move.is_white == my_is_white)
        .where(opp_rating.is_not(None), my_rating.is_not(None))
        .group_by("bucket")
    )).all()
    out = []
    for r in rows:
        if r.n < 30:
            continue
        rate = (r.bl or 0) / r.n
        rel = _rel(rate, baseline)
        out.append(Insight(
            metric="opponent_rating",
            bucket=r.bucket,
            blunder_rate=round(rate, 4),
            sample_moves=r.n,
            relative_to_baseline=round(rel, 2),
            comment=_comment("Force adverse", r.bucket, rel),
        ))
    return out


async def _phase_blunder(
    session: AsyncSession, player: Player, baseline: float
) -> list[Insight]:
    my_is_white = case(
        (Game.white_player_id == player.id, True),
        else_=False,
    )
    phase = case(
        (Move.ply <= 20, "opening"),
        (Move.ply <= 40, "middlegame"),
        else_="endgame",
    ).label("phase")
    rows = (await session.execute(
        select(
            phase,
            func.count(Move.id).label("n"),
            func.sum(case((MoveAnalysis.quality.in_(BLUNDER_QUALITIES), 1), else_=0)).label("bl"),
        )
        .join(Game, Game.id == Move.game_id)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Move.is_white == my_is_white)
        .group_by("phase")
    )).all()
    out = []
    for r in rows:
        if r.n < 30:
            continue
        rate = (r.bl or 0) / r.n
        rel = _rel(rate, baseline)
        out.append(Insight(
            metric="phase",
            bucket=r.phase,
            blunder_rate=round(rate, 4),
            sample_moves=r.n,
            relative_to_baseline=round(rel, 2),
            comment=_comment("Phase", r.phase, rel),
        ))
    return out


async def _time_pressure(
    session: AsyncSession, player: Player, baseline: float
) -> list[Insight]:
    my_is_white = case(
        (Game.white_player_id == player.id, True),
        else_=False,
    )
    bucket = case(
        (Move.clock_seconds < 30, "under_30s"),
        (Move.clock_seconds < 120, "under_2min"),
        else_="comfortable",
    ).label("bucket")
    rows = (await session.execute(
        select(
            bucket,
            func.count(Move.id).label("n"),
            func.sum(case((MoveAnalysis.quality.in_(BLUNDER_QUALITIES), 1), else_=0)).label("bl"),
        )
        .join(Game, Game.id == Move.game_id)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Move.is_white == my_is_white)
        .where(Move.clock_seconds.is_not(None))
        .group_by("bucket")
    )).all()
    out = []
    for r in rows:
        if r.n < 30:
            continue
        rate = (r.bl or 0) / r.n
        rel = _rel(rate, baseline)
        out.append(Insight(
            metric="clock",
            bucket=r.bucket,
            blunder_rate=round(rate, 4),
            sample_moves=r.n,
            relative_to_baseline=round(rel, 2),
            comment=_comment("Horloge", r.bucket, rel),
        ))
    return out


async def _hour_of_day(
    session: AsyncSession, player: Player, baseline: float
) -> list[Insight]:
    my_is_white = case(
        (Game.white_player_id == player.id, True),
        else_=False,
    )
    bucket = case(
        (extract("hour", Game.played_at) < 6, "night"),
        (extract("hour", Game.played_at) < 12, "morning"),
        (extract("hour", Game.played_at) < 18, "afternoon"),
        else_="evening",
    ).label("bucket")
    rows = (await session.execute(
        select(
            bucket,
            func.count(Move.id).label("n"),
            func.sum(case((MoveAnalysis.quality.in_(BLUNDER_QUALITIES), 1), else_=0)).label("bl"),
        )
        .join(Game, Game.id == Move.game_id)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Move.is_white == my_is_white)
        .where(Game.played_at.is_not(None))
        .group_by("bucket")
    )).all()
    out = []
    for r in rows:
        if r.n < 30:
            continue
        rate = (r.bl or 0) / r.n
        rel = _rel(rate, baseline)
        out.append(Insight(
            metric="hour_of_day",
            bucket=r.bucket,
            blunder_rate=round(rate, 4),
            sample_moves=r.n,
            relative_to_baseline=round(rel, 2),
            comment=_comment("Moment journée", r.bucket, rel),
        ))
    return out


async def analyse_context(session: AsyncSession, player: Player) -> ContextReport:
    n_blunders, n_total = await _baseline(session, player)
    baseline_rate = n_blunders / max(n_total, 1)
    report = ContextReport(
        baseline_blunder_rate=round(baseline_rate, 4),
        total_moves=n_total,
    )
    if n_total < 100:
        return report   # not enough data
    for fn in (_opponent_rating_delta, _phase_blunder, _time_pressure, _hour_of_day):
        report.insights.extend(await fn(session, player, baseline_rate))
    # Sort by relative size away from baseline (descending magnitude)
    report.insights.sort(key=lambda i: -abs(i.relative_to_baseline - 1.0))
    return report

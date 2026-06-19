"""Adaptive Stockfish ELO selection for the position trainer.

Heuristic — *not* Glicko, just enough signal to keep practice in the
"slightly above your level" sweet spot:

  - Look at the last N finished position_sessions.
  - Compute the user's score: wins + 0.5 * draws over N.
  - If score >= 0.65 → bump target ELO by `step_up`.
  - If score <= 0.35 → drop target ELO by `step_down`.
  - Else → keep last ELO used.
  - Honour absolute bounds [MIN_ELO .. MAX_ELO] from Stockfish UCI_Elo.
  - On a streak of 3+ losses, drop more aggressively to break frustration.
  - On a streak of 3+ wins, push more aggressively.

Bootstrap: with no history yet, return the player's current rapid rating
from games (if known) clipped to bounds; otherwise return 1200.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Player, PositionSession
from app.models.position_session import PositionSessionStatus


MIN_ELO = 1320
MAX_ELO = 3190
DEFAULT_ELO = 1200    # clipped to MIN_ELO on use


@dataclass
class DifficultyRecommendation:
    next_elo: int
    last_elo: int | None
    sessions_used: int
    score: float
    win_streak: int
    loss_streak: int
    reason: str


def _clip(v: int) -> int:
    return max(MIN_ELO, min(MAX_ELO, v))


async def _last_sessions(
    session: AsyncSession, player: Player, n: int = 10
) -> list[PositionSession]:
    rows = list((await session.execute(
        select(PositionSession)
        .where(PositionSession.player_id == player.id)
        .where(PositionSession.status.in_((
            PositionSessionStatus.USER_WON,
            PositionSessionStatus.DRAW,
            PositionSessionStatus.USER_LOST,
        )))
        .order_by(PositionSession.id.desc())
        .limit(n)
    )).scalars())
    rows.reverse()
    return rows


async def _player_rapid_rating(session: AsyncSession, player: Player) -> int | None:
    my_rating = case(
        (Game.white_player_id == player.id, Game.white_rating),
        else_=Game.black_rating,
    )
    return (await session.execute(
        select(my_rating)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Game.time_class == "rapid")
        .where(my_rating.is_not(None))
        .order_by(Game.played_at.desc())
        .limit(1)
    )).scalar()


def _streak(sessions: list[PositionSession]) -> tuple[int, int]:
    """Return (wins_in_a_row_at_end, losses_in_a_row_at_end)."""
    win = loss = 0
    for s in reversed(sessions):
        if s.status == PositionSessionStatus.USER_WON:
            if loss > 0: break
            win += 1
        elif s.status == PositionSessionStatus.USER_LOST:
            if win > 0: break
            loss += 1
        else:
            break
    return win, loss


async def recommend_next_elo(
    session: AsyncSession,
    player: Player,
    *,
    lookback: int = 10,
    step_up: int = 50,
    step_down: int = 50,
) -> DifficultyRecommendation:
    sessions = await _last_sessions(session, player, n=lookback)

    if not sessions:
        rapid = await _player_rapid_rating(session, player)
        target = _clip(rapid + 200 if rapid else DEFAULT_ELO)
        return DifficultyRecommendation(
            next_elo=target,
            last_elo=None,
            sessions_used=0,
            score=0.0,
            win_streak=0,
            loss_streak=0,
            reason=f"no prior sessions — bootstrap to {target}",
        )

    last_elo = sessions[-1].sf_elo or DEFAULT_ELO
    wins = sum(1 for s in sessions if s.status == PositionSessionStatus.USER_WON)
    draws = sum(1 for s in sessions if s.status == PositionSessionStatus.DRAW)
    score = (wins + 0.5 * draws) / len(sessions)

    win_streak, loss_streak = _streak(sessions)

    # Streak override
    if win_streak >= 3:
        target = last_elo + step_up * 2
        reason = f"win streak {win_streak} — accelerate +{step_up * 2}"
    elif loss_streak >= 3:
        target = last_elo - step_down * 2
        reason = f"loss streak {loss_streak} — pull back -{step_down * 2}"
    elif score >= 0.65:
        target = last_elo + step_up
        reason = f"score {score:.2f} ≥ 0.65 over last {len(sessions)} — bump +{step_up}"
    elif score <= 0.35:
        target = last_elo - step_down
        reason = f"score {score:.2f} ≤ 0.35 — drop -{step_down}"
    else:
        target = last_elo
        reason = f"score {score:.2f} in band — hold at {last_elo}"

    return DifficultyRecommendation(
        next_elo=_clip(target),
        last_elo=last_elo,
        sessions_used=len(sessions),
        score=round(score, 3),
        win_streak=win_streak,
        loss_streak=loss_streak,
        reason=reason,
    )

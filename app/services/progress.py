"""Take a snapshot of the player's current metrics.

Idempotent per day in the sense that running it multiple times the same day
overwrites the latest row for that day (we don't pile duplicates).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DailyPlan,
    Exercise,
    Game,
    MetricSnapshot,
    Player,
    RepertoireNode,
    Weakness,
)
from app.models.game import GameResult

logger = logging.getLogger(__name__)


async def take_snapshot(
    session: AsyncSession, player: Player, replace_today: bool = True
) -> MetricSnapshot:
    now = datetime.now(timezone.utc)
    today = now.date()

    # Optionally replace today's snapshot
    if replace_today:
        existing_today = list((await session.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.player_id == player.id)
            .where(func.date(MetricSnapshot.taken_at) == today)
        )).scalars())
        for row in existing_today:
            await session.delete(row)
        await session.flush()

    # Ratings
    def _latest_rating(time_class: str) -> int | None:
        my_rating = case(
            (Game.white_player_id == player.id, Game.white_rating),
            else_=Game.black_rating,
        )
        return None  # filled below

    async def _rating(time_class: str) -> int | None:
        my_rating = case(
            (Game.white_player_id == player.id, Game.white_rating),
            else_=Game.black_rating,
        )
        return (await session.execute(
            select(my_rating)
            .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
            .where(Game.time_class == time_class)
            .where(my_rating.is_not(None))
            .order_by(Game.played_at.desc())
            .limit(1)
        )).scalar()

    rapid = await _rating("rapid")
    blitz = await _rating("blitz")
    bullet = await _rating("bullet")

    # Game counts
    base_games = or_(Game.white_player_id == player.id, Game.black_player_id == player.id)
    games_total = (await session.execute(
        select(func.count(Game.id)).where(base_games)
    )).scalar_one()
    games_30d = (await session.execute(
        select(func.count(Game.id)).where(base_games).where(Game.played_at >= now - timedelta(days=30))
    )).scalar_one()
    games_7d = (await session.execute(
        select(func.count(Game.id)).where(base_games).where(Game.played_at >= now - timedelta(days=7))
    )).scalar_one()

    # Winrate per color
    result_expr = case(
        ((Game.white_player_id == player.id) & (Game.result == GameResult.WHITE_WIN), "win"),
        ((Game.black_player_id == player.id) & (Game.result == GameResult.BLACK_WIN), "win"),
        (Game.result == GameResult.DRAW, "draw"),
        else_="loss",
    )
    wr_rows = (await session.execute(
        select(
            case((Game.white_player_id == player.id, "white"), else_="black").label("color"),
            func.sum(case((result_expr == "win", 1), else_=0)).label("wins"),
            func.sum(case((result_expr == "draw", 1), else_=0)).label("draws"),
            func.count(Game.id).label("n"),
        )
        .where(base_games)
        .group_by("color")
    )).all()
    wr_by_color: dict[str, float | None] = {"white": None, "black": None}
    for r in wr_rows:
        if r.n:
            wr_by_color[r.color] = round((r.wins + 0.5 * r.draws) / r.n, 3)

    # Training engagement
    seven_d_ago = now - timedelta(days=7)
    exercises_solved_total = (await session.execute(
        select(func.coalesce(func.sum(Exercise.successes), 0))
        .where(or_(Exercise.player_id == player.id, Exercise.player_id.is_(None)))
    )).scalar_one()
    exercises_solved_7d = (await session.execute(
        select(func.count(Exercise.id))
        .where(Exercise.sr_last_reviewed_at >= seven_d_ago)
    )).scalar_one()
    rep_reviewed_7d = (await session.execute(
        select(func.count(RepertoireNode.id))
        .where(RepertoireNode.sr_last_reviewed_at >= seven_d_ago)
    )).scalar_one()
    plans_completed_7d = (await session.execute(
        select(func.count(DailyPlan.id))
        .where(DailyPlan.player_id == player.id)
        .where(DailyPlan.completed_at >= seven_d_ago)
    )).scalar_one()

    # Weakness severities snapshot
    w_rows = list((await session.execute(
        select(Weakness).where(Weakness.player_id == player.id)
    )).scalars())
    weakness_severities = {w.category: round(w.severity, 3) for w in w_rows}

    # Repertoire / exercise queue
    rep_due = (await session.execute(
        select(func.count(RepertoireNode.id))
        .where(RepertoireNode.sr_due_at.is_not(None), RepertoireNode.sr_due_at <= now)
    )).scalar_one()
    ex_due = (await session.execute(
        select(func.count(Exercise.id))
        .where(Exercise.sr_due_at.is_not(None), Exercise.sr_due_at <= now)
    )).scalar_one()

    snap = MetricSnapshot(
        player_id=player.id,
        taken_at=now,
        rating_rapid=rapid,
        rating_blitz=blitz,
        rating_bullet=bullet,
        games_total=games_total,
        games_30d=games_30d,
        games_7d=games_7d,
        winrate_white=wr_by_color.get("white"),
        winrate_black=wr_by_color.get("black"),
        exercises_solved_total=int(exercises_solved_total),
        exercises_solved_7d=exercises_solved_7d,
        rep_cards_reviewed_7d=rep_reviewed_7d,
        plans_completed_7d=plans_completed_7d,
        weakness_severities=weakness_severities,
        repertoire_due=rep_due,
        exercises_due=ex_due,
    )
    session.add(snap)
    await session.commit()
    logger.info(
        "snapshot taken player=%s rating_rapid=%s weaknesses=%d",
        player.chesscom_username, rapid, len(weakness_severities),
    )
    return snap

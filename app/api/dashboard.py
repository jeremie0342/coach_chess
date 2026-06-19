"""Aggregate dashboard endpoint — the home-screen feed for Unity.

Single round-trip returning:
  - current player metadata (ratings, recent activity)
  - top weaknesses sorted by severity
  - today's training load (repertoire cards + exercises due)
  - recent game summary (last 5 with quality flags)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Exercise, Game, Player, RepertoireNode, Weakness
from app.models.game import GameResult

router = APIRouter(tags=["dashboard"])


class PlayerHeader(BaseModel):
    chesscom_username: str
    games_total: int
    games_last_30d: int
    current_rating_rapid: int | None = None
    winrate_white: float | None = None
    winrate_black: float | None = None


class WeaknessSummary(BaseModel):
    category: str
    phase: str | None
    severity: float
    occurrences: int
    details: dict | None
    sample_game_ids: list[int] = Field(default_factory=list)


class TrainingLoad(BaseModel):
    repertoire_due: int
    repertoire_new_available: int
    exercises_due: int
    exercises_new_available: int


class RecentGame(BaseModel):
    id: int
    url: str | None
    played_at: datetime | None
    color: str
    result: str
    my_rating: int | None
    opening: str | None
    eco: str | None
    my_out_of_book_ply: int | None


class DashboardResponse(BaseModel):
    player: PlayerHeader
    weaknesses: list[WeaknessSummary]
    training: TrainingLoad
    recent_games: list[RecentGame]


@router.get(
    "/coach/me/dashboard",
    response_model=DashboardResponse,
    summary="Aggregated home-screen data for the current player",
)
async def dashboard(
    session: Annotated[AsyncSession, Depends(get_session)],
    weaknesses_limit: int = 5,
    recent_games_limit: int = 5,
) -> DashboardResponse:
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        from fastapi import HTTPException
        raise HTTPException(404, "current player not imported")

    now = datetime.now(timezone.utc)
    last_30d = now - timedelta(days=30)

    # --- Player header
    my_color = case(
        (Game.white_player_id == me.id, "white"),
        else_="black",
    )
    my_result = case(
        ((Game.white_player_id == me.id) & (Game.result == GameResult.WHITE_WIN), "win"),
        ((Game.black_player_id == me.id) & (Game.result == GameResult.BLACK_WIN), "win"),
        (Game.result == GameResult.DRAW, "draw"),
        else_="loss",
    )
    my_rating = case(
        (Game.white_player_id == me.id, Game.white_rating),
        else_=Game.black_rating,
    )

    games_total = (await session.execute(
        select(func.count()).where(or_(
            Game.white_player_id == me.id, Game.black_player_id == me.id
        ))
    )).scalar_one()
    games_30d = (await session.execute(
        select(func.count()).where(
            or_(Game.white_player_id == me.id, Game.black_player_id == me.id),
            Game.played_at >= last_30d,
        )
    )).scalar_one()

    # Most recent rapid rating
    rapid_rating = (await session.execute(
        select(my_rating)
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .where(Game.time_class == "rapid")
        .where(my_rating.is_not(None))
        .order_by(Game.played_at.desc())
        .limit(1)
    )).scalar()

    # Winrate per color
    wr_rows = (await session.execute(
        select(
            my_color.label("color"),
            func.sum(case((my_result == "win", 1), else_=0)).label("wins"),
            func.sum(case((my_result == "draw", 1), else_=0)).label("draws"),
            func.count(Game.id).label("n"),
        )
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .group_by("color")
    )).all()
    wr_by_color: dict[str, float] = {}
    for row in wr_rows:
        if row.n:
            wr_by_color[row.color] = (row.wins + 0.5 * row.draws) / row.n

    # --- Weaknesses (top by severity)
    w_rows = list((await session.execute(
        select(Weakness)
        .where(Weakness.player_id == me.id)
        .order_by(Weakness.severity.desc())
        .limit(weaknesses_limit)
    )).scalars())

    # --- Training load
    rep_due = (await session.execute(
        select(func.count(RepertoireNode.id))
        .where(RepertoireNode.is_my_move.is_(True))
        .where(RepertoireNode.sr_due_at.is_not(None), RepertoireNode.sr_due_at <= now)
    )).scalar_one()
    rep_new = (await session.execute(
        select(func.count(RepertoireNode.id))
        .where(RepertoireNode.is_my_move.is_(True))
        .where(RepertoireNode.sr_repetitions == 0)
    )).scalar_one()
    ex_due = (await session.execute(
        select(func.count(Exercise.id))
        .where(Exercise.sr_due_at.is_not(None), Exercise.sr_due_at <= now)
        .where(Exercise.sr_repetitions > 0)
    )).scalar_one()
    ex_new = (await session.execute(
        select(func.count(Exercise.id)).where(Exercise.sr_repetitions == 0)
    )).scalar_one()

    # --- Recent games
    from app.models.opening import Opening
    recent_q = (
        select(Game, Opening.name.label("op_name"))
        .outerjoin(Opening, Opening.id == Game.deepest_opening_id)
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .order_by(Game.played_at.desc())
        .limit(recent_games_limit)
    )
    recent_rows = (await session.execute(recent_q)).all()
    recent: list[RecentGame] = []
    for g, op_name in recent_rows:
        is_white = g.white_player_id == me.id
        if g.result == GameResult.DRAW:
            res = "draw"
        elif (is_white and g.result == GameResult.WHITE_WIN) or (
            not is_white and g.result == GameResult.BLACK_WIN
        ):
            res = "win"
        else:
            res = "loss"
        recent.append(RecentGame(
            id=g.id,
            url=g.url,
            played_at=g.played_at,
            color="white" if is_white else "black",
            result=res,
            my_rating=g.white_rating if is_white else g.black_rating,
            opening=op_name or g.opening_name,
            eco=g.eco,
            my_out_of_book_ply=g.my_out_of_book_ply,
        ))

    return DashboardResponse(
        player=PlayerHeader(
            chesscom_username=me.chesscom_username,
            games_total=games_total,
            games_last_30d=games_30d,
            current_rating_rapid=rapid_rating,
            winrate_white=round(wr_by_color["white"], 3) if "white" in wr_by_color else None,
            winrate_black=round(wr_by_color["black"], 3) if "black" in wr_by_color else None,
        ),
        weaknesses=[
            WeaknessSummary(
                category=w.category,
                phase=w.phase,
                severity=round(w.severity, 3),
                occurrences=w.occurrences,
                details=w.details,
                sample_game_ids=(w.sample_game_ids or [])[:5],
            )
            for w in w_rows
        ],
        training=TrainingLoad(
            repertoire_due=rep_due,
            repertoire_new_available=rep_new,
            exercises_due=ex_due,
            exercises_new_available=ex_new,
        ),
        recent_games=recent,
    )

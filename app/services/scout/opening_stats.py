"""Compute an opponent's opening profile from their stored games.

We look at the first ~6 plies to characterise what they play and how they
fare with each line.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, Opening, Player
from app.models.game import GameResult


@dataclass
class MoveStat:
    uci: str
    san: str
    games: int
    wins: int
    losses: int
    draws: int

    @property
    def winrate(self) -> float:
        return (self.wins + 0.5 * self.draws) / max(self.games, 1)


@dataclass
class OpeningStat:
    eco: str | None
    name: str | None
    games: int
    winrate: float


@dataclass
class OpponentOpeningReport:
    player_username: str
    games_seen: int
    avg_out_of_book_ply: float | None
    first_move_as_white: list[MoveStat] = field(default_factory=list)
    response_to_e4: list[MoveStat] = field(default_factory=list)
    response_to_d4: list[MoveStat] = field(default_factory=list)
    response_to_nf3: list[MoveStat] = field(default_factory=list)
    top_openings_white: list[OpeningStat] = field(default_factory=list)
    top_openings_black: list[OpeningStat] = field(default_factory=list)


def _result_case(player_id: int):
    return case(
        ((Game.white_player_id == player_id) & (Game.result == GameResult.WHITE_WIN), "win"),
        ((Game.black_player_id == player_id) & (Game.result == GameResult.BLACK_WIN), "win"),
        (Game.result == GameResult.DRAW, "draw"),
        else_="loss",
    )


async def _aggregate_moves(
    session: AsyncSession,
    player_id: int,
    color: str,
    ply: int,
    constraint_move: tuple[int, str] | None = None,
    top: int = 5,
) -> list[MoveStat]:
    """Aggregate the player's move at `ply` when they're `color`.

    constraint_move=(ply_X, uci_X) restricts to games where Move at ply_X had uci_X.
    Useful for "response to 1.e4 as Black" (ply=2, when ply=1 was e2e4).
    """
    result = _result_case(player_id)
    color_filter = (
        Game.white_player_id == player_id if color == "white"
        else Game.black_player_id == player_id
    )

    q = (
        select(
            Move.uci,
            Move.san,
            func.count(Game.id).label("n"),
            func.sum(case((result == "win", 1), else_=0)).label("wins"),
            func.sum(case((result == "loss", 1), else_=0)).label("losses"),
            func.sum(case((result == "draw", 1), else_=0)).label("draws"),
        )
        .join(Game, Game.id == Move.game_id)
        .where(color_filter)
        .where(Move.ply == ply)
    )
    if constraint_move:
        cply, cuci = constraint_move
        constraint_subq = (
            select(Move.game_id)
            .where(Move.ply == cply, Move.uci == cuci)
            .subquery()
        )
        q = q.where(Move.game_id.in_(select(constraint_subq)))
    q = q.group_by(Move.uci, Move.san).order_by(func.count(Game.id).desc()).limit(top)

    rows = (await session.execute(q)).all()
    return [
        MoveStat(uci=r.uci, san=r.san, games=r.n, wins=r.wins, losses=r.losses, draws=r.draws)
        for r in rows
    ]


async def _aggregate_openings(
    session: AsyncSession, player_id: int, color: str, top: int = 5
) -> list[OpeningStat]:
    result = _result_case(player_id)
    color_filter = (
        Game.white_player_id == player_id if color == "white"
        else Game.black_player_id == player_id
    )
    q = (
        select(
            Opening.eco,
            Opening.name,
            func.count(Game.id).label("n"),
            func.sum(case((result == "win", 1), else_=0)).label("wins"),
            func.sum(case((result == "draw", 1), else_=0)).label("draws"),
        )
        .join(Opening, Opening.id == Game.deepest_opening_id)
        .where(color_filter)
        .group_by(Opening.eco, Opening.name)
        .order_by(func.count(Game.id).desc())
        .limit(top)
    )
    rows = (await session.execute(q)).all()
    out = []
    for r in rows:
        wr = (r.wins + 0.5 * r.draws) / max(r.n, 1)
        out.append(OpeningStat(eco=r.eco, name=r.name, games=r.n, winrate=round(wr, 3)))
    return out


async def compute_opening_report(
    session: AsyncSession, player: Player
) -> OpponentOpeningReport:
    from sqlalchemy import or_
    games_seen = (await session.execute(
        select(func.count(Game.id))
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
    )).scalar_one()

    avg_oob = (await session.execute(
        select(func.avg(Game.my_out_of_book_ply))
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Game.my_out_of_book_ply.is_not(None))
    )).scalar()

    return OpponentOpeningReport(
        player_username=player.chesscom_username,
        games_seen=games_seen,
        avg_out_of_book_ply=float(avg_oob) if avg_oob else None,
        first_move_as_white=await _aggregate_moves(session, player.id, "white", ply=1),
        response_to_e4=await _aggregate_moves(session, player.id, "black", ply=2, constraint_move=(1, "e2e4")),
        response_to_d4=await _aggregate_moves(session, player.id, "black", ply=2, constraint_move=(1, "d2d4")),
        response_to_nf3=await _aggregate_moves(session, player.id, "black", ply=2, constraint_move=(1, "g1f3")),
        top_openings_white=await _aggregate_openings(session, player.id, "white"),
        top_openings_black=await _aggregate_openings(session, player.id, "black"),
    )

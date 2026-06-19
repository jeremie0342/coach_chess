from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Game, Player, RepertoireNode
from app.models.repertoire import RepertoireColor
from app.services.openings.out_of_book import (
    compute_out_of_book_for_all_my_games,
    compute_out_of_book_for_game,
)
from app.services.openings.repertoire_builder import build_repertoire
from app.services.openings.theory import match_position

router = APIRouter(tags=["repertoire"])


async def _get_me(session: AsyncSession) -> Player:
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "Current player not yet imported.")
    return me


@router.post("/repertoire/me/rebuild")
async def rebuild_repertoire(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = await _get_me(session)
    return await build_repertoire(session, me)


@router.get("/repertoire/me/summary")
async def repertoire_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = await _get_me(session)
    counts = (await session.execute(
        select(RepertoireNode.color, func.count(RepertoireNode.id))
        .group_by(RepertoireNode.color)
    )).all()
    return {
        "player": me.chesscom_username,
        "nodes_by_color": {str(c): n for c, n in counts},
    }


@router.get("/repertoire/me/top-lines")
async def top_lines(
    session: Annotated[AsyncSession, Depends(get_session)],
    color: RepertoireColor,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
) -> dict:
    me = await _get_me(session)
    rows = list((await session.execute(
        select(RepertoireNode)
        .where(RepertoireNode.color == color)
        .order_by(RepertoireNode.created_at.asc())
        .limit(limit)
    )).scalars())
    return {
        "player": me.chesscom_username,
        "color": str(color),
        "lines": [
            {
                "id": n.id,
                "fen": n.fen,
                "my_move_san": n.move_san,
                "my_move_uci": n.move_uci,
                "label": n.label,
                "notes": n.notes,
            }
            for n in rows
        ],
    }


@router.get("/openings/match")
async def openings_match(
    session: Annotated[AsyncSession, Depends(get_session)],
    fen: str,
) -> dict:
    m = await match_position(session, fen)
    if not m:
        return {"matched": False, "fen": fen}
    return {
        "matched": True,
        "opening_id": m.opening_id,
        "eco": m.eco,
        "name": m.name,
        "moves_san": m.moves_san,
    }


@router.post("/games/{game_id}/out_of_book")
async def game_out_of_book(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")
    me = await _get_me(session)
    result = await compute_out_of_book_for_game(session, game, me_player_id=me.id)
    await session.commit()
    return result


@router.post("/repertoire/me/recompute_out_of_book")
async def recompute_all_out_of_book(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = await _get_me(session)
    return await compute_out_of_book_for_all_my_games(session, me)

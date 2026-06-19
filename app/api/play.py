from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Player, PositionSession, PositionSessionMove
from app.services.play_engine import (
    abandon_session,
    apply_user_move,
    start_session,
)

router = APIRouter(prefix="/train/play", tags=["play"])


class StartPlayIn(BaseModel):
    fen: str = Field(..., description="Starting position FEN")
    user_color: str = Field(..., description="'white' or 'black'")
    skill_level: int = Field(10, ge=0, le=20)
    sf_elo: int | None = Field(None, ge=1320, le=3190)
    depth: int = Field(12, ge=4, le=25)
    title: str | None = None
    source: str | None = None


class MoveIn(BaseModel):
    move: str


def _serialize(sess: PositionSession, moves: list[PositionSessionMove]) -> dict:
    return {
        "id": sess.id,
        "title": sess.title,
        "user_color": sess.user_color,
        "starting_fen": sess.starting_fen,
        "current_fen": sess.current_fen,
        "status": str(sess.status),
        "result_reason": sess.result_reason,
        "ply": sess.final_ply,
        "sf_skill_level": sess.sf_skill_level,
        "sf_elo": sess.sf_elo,
        "moves": [
            {
                "ply": m.ply,
                "is_user": m.is_user,
                "san": m.san,
                "uci": m.uci,
                "fen_after": m.fen_after,
                "eval_cp": m.eval_cp_after,
                "eval_mate": m.eval_mate_after,
            }
            for m in moves
        ],
    }


async def _load_moves(session: AsyncSession, sess_id: int) -> list[PositionSessionMove]:
    return list((await session.execute(
        select(PositionSessionMove)
        .where(PositionSessionMove.session_id == sess_id)
        .order_by(PositionSessionMove.ply)
    )).scalars())


@router.post("/start")
async def start(
    payload: StartPlayIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    try:
        sess = await start_session(
            session,
            starting_fen=payload.fen,
            user_color=payload.user_color,
            skill_level=payload.skill_level,
            sf_elo=payload.sf_elo,
            depth=payload.depth,
            title=payload.title,
            source=payload.source,
            player_id=me.id if me else None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    moves = await _load_moves(session, sess.id)
    return _serialize(sess, moves)


@router.get("/{session_id}")
async def get_session_state(
    session_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    sess = (await session.execute(
        select(PositionSession).where(PositionSession.id == session_id)
    )).scalar_one_or_none()
    if not sess:
        raise HTTPException(404, "session not found")
    moves = await _load_moves(session, sess.id)
    return _serialize(sess, moves)


@router.post("/{session_id}/move")
async def make_move(
    session_id: int,
    payload: MoveIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    sess = (await session.execute(
        select(PositionSession).where(PositionSession.id == session_id)
    )).scalar_one_or_none()
    if not sess:
        raise HTTPException(404, "session not found")
    result = await apply_user_move(session, sess, payload.move)
    moves = await _load_moves(session, sess.id)
    return {
        "accepted": result.accepted,
        "error": result.error,
        "user_uci": result.user_uci,
        "user_san": result.user_san,
        "engine_uci": result.engine_uci,
        "engine_san": result.engine_san,
        "current_fen": sess.current_fen,
        "status": str(sess.status),
        "eval_cp": result.eval_cp,
        "eval_mate": result.eval_mate,
        "moves": [
            {"ply": m.ply, "is_user": m.is_user, "san": m.san, "uci": m.uci}
            for m in moves
        ],
    }


@router.post("/{session_id}/abandon")
async def abandon(
    session_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    sess = (await session.execute(
        select(PositionSession).where(PositionSession.id == session_id)
    )).scalar_one_or_none()
    if not sess:
        raise HTTPException(404, "session not found")
    await abandon_session(session, sess)
    return {"id": sess.id, "status": str(sess.status)}

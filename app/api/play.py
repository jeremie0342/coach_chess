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
    undo_last_user_move,
)

router = APIRouter(prefix="/train/play", tags=["play"])


@router.get("/openings", summary="List openings available to enforce in a constrained play session")
async def list_constrained_openings() -> dict:
    from app.services import opening_trainer as ot
    return {
        "openings": [
            {
                "key": op.key,
                "name": op.name,
                "base_name": op.base_name,
                "eco": op.eco,
                "user_color": op.user_color,
                "summary": op.summary,
                "plies": len(op.moves),
                "branch_count": len(op.branches),
                "branches": [b.label for b in op.branches],
            }
            for op in ot.LIBRARY.values()
        ]
    }


class StartPlayIn(BaseModel):
    fen: str = Field(..., description="Starting position FEN")
    user_color: str = Field(..., description="'white' or 'black'")
    skill_level: int = Field(10, ge=0, le=20)
    sf_elo: int | None = Field(None, ge=1320, le=3190)
    depth: int = Field(12, ge=4, le=25)
    title: str | None = None
    source: str | None = None
    source_ref: dict | None = None
    # Take-back budget. 0 = strict (no undo), use 999 for unlimited.
    max_undos: int = Field(0, ge=0, le=999)
    # Optional: enforce a specific opening line. Stockfish picks a random branch
    # at session start (mainline or any registered branch). The user must
    # follow the prescribed moves until the line is exhausted.
    opening_key: str | None = None


class MoveIn(BaseModel):
    move: str


def _serialize(sess: PositionSession, moves: list[PositionSessionMove]) -> dict:
    # NOTE: we intentionally do NOT surface the next expected move while the
    # session is in_book — the whole point of the drill is to recall the line
    # from memory. The expected move is only revealed by the backend in the
    # error message AFTER a deviation.
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
        "max_undos": sess.max_undos,
        "undos_used": sess.undos_used,
        "undos_remaining": max(0, sess.max_undos - sess.undos_used),
        "source": sess.source,
        "source_ref": sess.source_ref,
        "opening_key": sess.opening_key,
        "opening_branch_label": sess.opening_branch_label,
        "opening_status": sess.opening_status,
        "opening_ply_index": sess.opening_ply_index,
        "opening_total_plies": len(sess.opening_moves) if sess.opening_moves else 0,
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
            source_ref=payload.source_ref,
            max_undos=payload.max_undos,
            player_id=me.id if me else None,
            opening_key=payload.opening_key,
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
        "user_captured": result.user_captured,
        "engine_captured": result.engine_captured,
        "in_check_after_user": result.in_check_after_user,
        "in_check_after_engine": result.in_check_after_engine,
        "best_user_uci": result.best_user_uci,
        "best_user_san": result.best_user_san,
        "user_cp_loss": result.user_cp_loss,
        "user_quality": result.user_quality,
        "opening_status": sess.opening_status,
        "opening_ply_index": sess.opening_ply_index,
        "opening_total_plies": len(sess.opening_moves) if sess.opening_moves else 0,
        "undos_used": sess.undos_used,
        "undos_remaining": max(0, sess.max_undos - sess.undos_used),
        "result_reason": sess.result_reason,
        "moves": [
            {"ply": m.ply, "is_user": m.is_user, "san": m.san, "uci": m.uci}
            for m in moves
        ],
    }


@router.get("/{session_id}/legal")
async def legal_moves(
    session_id: int,
    square: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    import chess as _ch
    sess = (await session.execute(
        select(PositionSession).where(PositionSession.id == session_id)
    )).scalar_one_or_none()
    if not sess:
        raise HTTPException(404, "session not found")
    board = _ch.Board(sess.current_fen)
    sq = (square or "").strip().lower()
    if len(sq) != 2 or sq[0] not in "abcdefgh" or sq[1] not in "12345678":
        raise HTTPException(400, "square must be like 'e2'")
    src = _ch.parse_square(sq)
    piece = board.piece_at(src)
    if piece is None:
        return {"from": sq, "to": [], "in_check": board.is_check(), "side_to_move": "white" if board.turn else "black", "owner": None}
    destinations = []
    promo_destinations = []
    for m in board.legal_moves:
        if m.from_square == src:
            dest = _ch.square_name(m.to_square)
            if m.promotion is not None:
                if dest not in promo_destinations:
                    promo_destinations.append(dest)
            else:
                if dest not in destinations:
                    destinations.append(dest)
    owner = "white" if piece.color == _ch.WHITE else "black"
    return {
        "from": sq,
        "to": destinations + promo_destinations,
        "promotions": promo_destinations,
        "owner": owner,
        "in_check": board.is_check(),
        "side_to_move": "white" if board.turn else "black",
    }


@router.post("/{session_id}/undo", summary="Take back the last (user, engine) move pair")
async def undo(
    session_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    sess = (await session.execute(
        select(PositionSession).where(PositionSession.id == session_id)
    )).scalar_one_or_none()
    if not sess:
        raise HTTPException(404, "session not found")
    r = await undo_last_user_move(session, sess)
    moves = await _load_moves(session, sess.id)
    return {
        "accepted": r.accepted,
        "error": r.error,
        "current_fen": r.current_fen,
        "undos_used": r.undos_used,
        "undos_remaining": r.undos_remaining,
        "plies_popped": r.plies_popped,
        "moves": [{"ply": m.ply, "is_user": m.is_user, "san": m.san, "uci": m.uci} for m in moves],
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

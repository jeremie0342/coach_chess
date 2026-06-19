from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Exercise, Game, Move
from app.services.position_card import CardOptions, render_card
from app.services.position_gif import (
    GifFrame, GifOptions, frames_from_moves, render_gif,
)

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/position.png", responses={200: {"content": {"image/png": {}}}})
async def position_card(
    fen: str,
    title: str = "Coach chess",
    subtitle: str | None = None,
    best: str | None = None,
    eval_cp: int | None = None,
    eval_mate: int | None = None,
    side_label: str | None = None,
    themes: Annotated[list[str] | None, Query()] = None,
    footer: str = "coach_chess",
    board_size: Annotated[int, Query(ge=200, le=1200)] = 600,
) -> Response:
    try:
        png = render_card(fen, CardOptions(
            title=title,
            subtitle=subtitle,
            best_move_uci=best,
            eval_cp=eval_cp,
            eval_mate=eval_mate,
            side_to_move_label=side_label,
            themes=themes,
            footer=footer,
            board_size=board_size,
        ))
    except Exception as e:
        raise HTTPException(400, f"failed to render: {e}")
    return Response(content=png, media_type="image/png")


@router.get("/game.gif", responses={200: {"content": {"image/gif": {}}}})
async def game_gif(
    session: Annotated[AsyncSession, Depends(get_session)],
    game_id: int,
    start_ply: int = 1,
    end_ply: int | None = None,
    frame_ms: Annotated[int, Query(ge=200, le=5000)] = 900,
    board_size: Annotated[int, Query(ge=240, le=800)] = 480,
) -> Response:
    game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")
    moves = list((await session.execute(
        select(Move).where(Move.game_id == game_id).order_by(Move.ply)
    )).scalars())
    if end_ply is None:
        end_ply = len(moves)
    selected = [m for m in moves if start_ply <= m.ply <= end_ply]
    if not selected:
        raise HTTPException(400, "empty ply range")
    initial = selected[0].fen_before
    moves_uci = [m.uci for m in selected]
    captions = [f"{m.move_number}.{'..' if not m.is_white else ''} {m.san}" for m in selected]
    frames = frames_from_moves(initial, moves_uci, captions)
    gif = render_gif(frames, GifOptions(frame_duration_ms=frame_ms, board_size=board_size))
    return Response(content=gif, media_type="image/gif")


@router.get("/exercise.gif", responses={200: {"content": {"image/gif": {}}}})
async def exercise_gif(
    session: Annotated[AsyncSession, Depends(get_session)],
    exercise_id: int,
    frame_ms: Annotated[int, Query(ge=200, le=5000)] = 1100,
    board_size: Annotated[int, Query(ge=240, le=800)] = 480,
) -> Response:
    ex = (await session.execute(select(Exercise).where(Exercise.id == exercise_id))).scalar_one_or_none()
    if not ex:
        raise HTTPException(404, "exercise not found")
    frames = frames_from_moves(ex.fen, ex.solution_uci or [], None)
    if not frames:
        raise HTTPException(400, "no solution moves")
    # Caption the very first frame with the puzzle title
    if ex.title:
        frames[0].caption = ex.title
    gif = render_gif(frames, GifOptions(frame_duration_ms=frame_ms, board_size=board_size))
    return Response(content=gif, media_type="image/gif")

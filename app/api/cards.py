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
    GifFrame, GifOptions, frames_from_moves, render_gif, render_mp4,
)

router = APIRouter(prefix="/cards", tags=["cards"])


def _safe_filename(stem: str, ext: str) -> str:
    """Sanitize a stem to a safe filename (ASCII only)."""
    clean = "".join(c for c in stem if c.isalnum() or c in ("-", "_"))[:64]
    if not clean:
        clean = "coach_chess"
    return f"{clean}.{ext}"


def _attach_headers(filename: str, download: bool) -> dict:
    disposition = "attachment" if download else "inline"
    return {"Content-Disposition": f'{disposition}; filename="{filename}"'}


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
    download: Annotated[bool, Query(description="Force browser to download instead of display inline")] = False,
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
    filename = _safe_filename(title or "position", "png")
    return Response(
        content=png,
        media_type="image/png",
        headers=_attach_headers(filename, download),
    )


@router.get("/game.gif", responses={200: {"content": {"image/gif": {}}}})
async def game_gif(
    session: Annotated[AsyncSession, Depends(get_session)],
    game_id: int,
    start_ply: int = 1,
    end_ply: int | None = None,
    frame_ms: Annotated[int, Query(ge=200, le=5000)] = 900,
    board_size: Annotated[int, Query(ge=240, le=800)] = 480,
    download: Annotated[bool, Query()] = False,
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
    filename = _safe_filename(f"game_{game_id}", "gif")
    return Response(
        content=gif, media_type="image/gif",
        headers=_attach_headers(filename, download),
    )


@router.get("/game.mp4", responses={200: {"content": {"video/mp4": {}}}})
async def game_mp4(
    session: Annotated[AsyncSession, Depends(get_session)],
    game_id: int,
    start_ply: int = 1,
    end_ply: int | None = None,
    frame_ms: Annotated[int, Query(ge=200, le=5000)] = 900,
    board_size: Annotated[int, Query(ge=240, le=1200)] = 720,
    download: Annotated[bool, Query()] = False,
) -> Response:
    """Same as game.gif but encoded as MP4 (H.264). Smaller, pausable, scrubbable."""
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
    mp4 = render_mp4(frames, GifOptions(frame_duration_ms=frame_ms, board_size=board_size))
    filename = _safe_filename(f"game_{game_id}", "mp4")
    return Response(
        content=mp4, media_type="video/mp4",
        headers=_attach_headers(filename, download),
    )


@router.get("/exercise.gif", responses={200: {"content": {"image/gif": {}}}})
async def exercise_gif(
    session: Annotated[AsyncSession, Depends(get_session)],
    exercise_id: int,
    frame_ms: Annotated[int, Query(ge=200, le=5000)] = 1100,
    board_size: Annotated[int, Query(ge=240, le=800)] = 480,
    download: Annotated[bool, Query()] = False,
) -> Response:
    ex = (await session.execute(select(Exercise).where(Exercise.id == exercise_id))).scalar_one_or_none()
    if not ex:
        raise HTTPException(404, "exercise not found")
    frames = frames_from_moves(ex.fen, ex.solution_uci or [], None)
    if not frames:
        raise HTTPException(400, "no solution moves")
    if ex.title:
        frames[0].caption = ex.title
    gif = render_gif(frames, GifOptions(frame_duration_ms=frame_ms, board_size=board_size))
    filename = _safe_filename(f"puzzle_{exercise_id}", "gif")
    return Response(
        content=gif, media_type="image/gif",
        headers=_attach_headers(filename, download),
    )


@router.get("/exercise.mp4", responses={200: {"content": {"video/mp4": {}}}})
async def exercise_mp4(
    session: Annotated[AsyncSession, Depends(get_session)],
    exercise_id: int,
    frame_ms: Annotated[int, Query(ge=200, le=5000)] = 1100,
    board_size: Annotated[int, Query(ge=240, le=1200)] = 720,
    download: Annotated[bool, Query()] = False,
) -> Response:
    ex = (await session.execute(select(Exercise).where(Exercise.id == exercise_id))).scalar_one_or_none()
    if not ex:
        raise HTTPException(404, "exercise not found")
    frames = frames_from_moves(ex.fen, ex.solution_uci or [], None)
    if not frames:
        raise HTTPException(400, "no solution moves")
    if ex.title:
        frames[0].caption = ex.title
    mp4 = render_mp4(frames, GifOptions(frame_duration_ms=frame_ms, board_size=board_size))
    filename = _safe_filename(f"puzzle_{exercise_id}", "mp4")
    return Response(
        content=mp4, media_type="video/mp4",
        headers=_attach_headers(filename, download),
    )

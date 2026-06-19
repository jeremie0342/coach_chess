from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import Game
from app.models.move import Move
from app.services.pgn_exporter import (
    ExportOptions,
    _cached_llm_comment,
    export_annotated_pgn,
    export_with_fresh_llm,
)

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

router = APIRouter(tags=["export"])


@router.get(
    "/games/{game_id}/annotated.pgn",
    response_class=PlainTextResponse,
    summary="Annotated PGN with Stockfish evals + LLM coach comments",
)
async def annotated_pgn(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    include_llm: bool = False,
    llm_only_worst: Annotated[int, Query(ge=0, le=20)] = 5,
    include_eval: bool = True,
    include_best_move_hint: bool = True,
    warm_llm: bool = False,
) -> PlainTextResponse:
    game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")
    opts = ExportOptions(
        include_llm=include_llm,
        llm_only_worst=llm_only_worst,
        include_eval=include_eval,
        include_best_move_hint=include_best_move_hint,
    )
    if warm_llm:
        # Slow: triggers LLM generation if cache is cold
        pgn = await export_with_fresh_llm(session, game, max_explanations=llm_only_worst)
    else:
        pgn = await export_annotated_pgn(session, game, opts)
    return PlainTextResponse(
        pgn,
        media_type="application/x-chess-pgn",
        headers={"Content-Disposition": f'attachment; filename="game_{game_id}.pgn"'},
    )


class TacticalMotifsResponse(BaseModel):
    ply: int
    motifs: list[dict]


@router.get(
    "/games/{game_id}/tactical_motifs",
    response_model=TacticalMotifsResponse,
    summary="Concrete squares involved in tactical motifs at a given ply",
)
async def tactical_motifs(
    game_id: int,
    ply: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TacticalMotifsResponse:
    from app.services.tactical_geometry import collect_motifs

    move = (await session.execute(
        select(Move)
        .where(Move.game_id == game_id, Move.ply == ply)
        .options(selectinload(Move.analysis))
    )).scalar_one_or_none()
    if not move:
        raise HTTPException(404, "move not found")
    a = move.analysis
    if a is None:
        return TacticalMotifsResponse(ply=ply, motifs=[])
    motifs = collect_motifs(
        tags=a.tags or [],
        fen_before=move.fen_before,
        played_uci=move.uci,
        best_uci=a.best_move_uci,
        pv_uci=a.pv,
    )
    return TacticalMotifsResponse(ply=ply, motifs=[m.to_dict() for m in motifs])


class LatestGame(BaseModel):
    id: int


@router.get("/games/latest", response_model=LatestGame, summary="Most recent imported game id")
async def latest_game(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LatestGame:
    g = (await session.execute(
        select(Game).order_by(Game.played_at.desc().nullslast()).limit(1)
    )).scalar_one_or_none()
    if not g:
        raise HTTPException(404, "no games imported")
    return LatestGame(id=g.id)


class AnalyzedMove(BaseModel):
    ply: int
    move_number: int
    is_white: bool
    san: str
    uci: str
    fen_before: str
    fen_after: str
    eval_cp: int | None = None
    eval_mate: int | None = None
    quality: str | None = None
    cp_loss: int | None = None
    best_uci: str | None = None
    best_san: str | None = None
    tags: list[str] = []
    coach_comment: str | None = None


class AnalyzedGame(BaseModel):
    id: int
    starting_fen: str
    white: str | None = None
    black: str | None = None
    result: str
    eco: str | None = None
    opening_name: str | None = None
    moves: list[AnalyzedMove]


@router.get(
    "/games/{game_id}/analysis.json",
    response_model=AnalyzedGame,
    summary="Structured JSON of moves + evals + tags + cached LLM comments",
)
async def analysis_json(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    include_llm: bool = True,
) -> AnalyzedGame:
    game = (
        await session.execute(
            select(Game)
            .where(Game.id == game_id)
            .options(
                selectinload(Game.white_player),
                selectinload(Game.black_player),
            )
        )
    ).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")

    moves = list((await session.execute(
        select(Move)
        .where(Move.game_id == game_id)
        .order_by(Move.ply)
        .options(selectinload(Move.analysis))
    )).scalars())

    out_moves: list[AnalyzedMove] = []
    for m in moves:
        a = m.analysis
        comment = None
        best_uci = a.best_move_uci if a else None
        if include_llm and a is not None:
            comment = _cached_llm_comment(m.fen_before, m.uci, best_uci)
        out_moves.append(AnalyzedMove(
            ply=m.ply,
            move_number=m.move_number,
            is_white=m.is_white,
            san=m.san,
            uci=m.uci,
            fen_before=m.fen_before,
            fen_after=m.fen_after,
            eval_cp=a.eval_cp if a else None,
            eval_mate=a.eval_mate if a else None,
            quality=str(a.quality) if (a and a.quality) else None,
            cp_loss=a.cp_loss if a else None,
            best_uci=best_uci,
            best_san=a.best_move_san if a else None,
            tags=(a.tags or []) if a else [],
            coach_comment=comment,
        ))

    return AnalyzedGame(
        id=game.id,
        starting_fen=game.initial_fen or STARTING_FEN,
        white=getattr(game.white_player, "chesscom_username", None) if game.white_player_id else None,
        black=getattr(game.black_player, "chesscom_username", None) if game.black_player_id else None,
        result=str(game.result),
        eco=game.eco,
        opening_name=game.opening_name,
        moves=out_moves,
    )

"""Builders for test data.

Keep these dumb and explicit — no random faker magic — so failures are
reproducible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import chess
import chess.pgn
import io

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, MoveAnalysis, Opening, Player
from app.models.analysis import MoveQuality
from app.models.game import GameResult, TimeControlCategory


async def make_player(
    session: AsyncSession,
    username: str = "tester",
    is_me: bool = True,
) -> Player:
    p = Player(chesscom_username=username, display_name=username, is_me=is_me)
    session.add(p)
    await session.flush()
    return p


async def make_opening(
    session: AsyncSession,
    eco: str = "C50",
    name: str = "Italian Game",
    moves_san: str = "1. e4 e5 2. Nf3 Nc6 3. Bc4",
    moves_uci: str = "e2e4 e7e5 g1f3 b8c6 f1c4",
    fen_signature: str = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq -",
) -> Opening:
    op = Opening(
        eco=eco, name=name, moves_san=moves_san,
        moves_uci=moves_uci, fen_signature=fen_signature,
    )
    session.add(op)
    await session.flush()
    return op


async def make_game(
    session: AsyncSession,
    white: Player,
    black: Player,
    *,
    pgn: str = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *",
    result: GameResult = GameResult.WHITE_WIN,
    white_rating: int = 450,
    black_rating: int = 450,
    eco: str | None = "C60",
    time_class: TimeControlCategory = TimeControlCategory.RAPID,
    external_id: str | None = None,
    played_at: datetime | None = None,
    populate_moves: bool = True,
) -> Game:
    game = Game(
        external_id=external_id or f"test_{id(white)}_{id(black)}",
        source="test",
        url=None,
        white_player_id=white.id,
        black_player_id=black.id,
        white_rating=white_rating,
        black_rating=black_rating,
        result=result,
        time_control="900+10",
        time_class=time_class,
        rated=True,
        eco=eco,
        pgn=pgn,
        played_at=played_at or datetime.now(timezone.utc),
        analysis_status="pending",
    )
    session.add(game)
    await session.flush()

    if populate_moves:
        await _populate_moves_from_pgn(session, game, pgn)
    return game


async def _populate_moves_from_pgn(
    session: AsyncSession, game: Game, pgn: str
) -> None:
    pgn_game = chess.pgn.read_game(io.StringIO(pgn))
    if not pgn_game:
        return
    board = pgn_game.board()
    node = pgn_game
    ply = 0
    while node.variations:
        nxt = node.variation(0)
        mv = nxt.move
        if mv is None:
            break
        fen_before = board.fen()
        san = board.san(mv)
        is_white = board.turn == chess.WHITE
        move_number = board.fullmove_number
        board.push(mv)
        ply += 1
        session.add(Move(
            game_id=game.id,
            ply=ply,
            move_number=move_number,
            is_white=is_white,
            san=san,
            uci=mv.uci(),
            fen_before=fen_before,
            fen_after=board.fen(),
        ))
        node = nxt
    game.ply_count = ply
    await session.flush()


async def attach_analysis(
    session: AsyncSession,
    move: Move,
    *,
    quality: MoveQuality = MoveQuality.GOOD,
    cp_loss: int | None = 0,
    eval_cp: int | None = 0,
    eval_cp_before: int | None = 0,
    eval_mate: int | None = None,
    eval_mate_before: int | None = None,
    best_move_uci: str | None = None,
    best_move_san: str | None = None,
    pv: list[str] | None = None,
    tags: list[str] | None = None,
) -> MoveAnalysis:
    ma = MoveAnalysis(
        move_id=move.id,
        depth=20,
        eval_cp=eval_cp,
        eval_mate=eval_mate,
        eval_cp_before=eval_cp_before,
        eval_mate_before=eval_mate_before,
        cp_loss=cp_loss,
        quality=quality,
        best_move_uci=best_move_uci,
        best_move_san=best_move_san,
        pv=pv,
        tags=tags,
    )
    session.add(ma)
    await session.flush()
    return ma

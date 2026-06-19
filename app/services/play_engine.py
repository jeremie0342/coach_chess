"""Play-out-a-position service: user vs Stockfish from any starting FEN.

Stockfish strength is controlled via two UCI options:
  - Skill Level (0..20): coarse strength reduction
  - UCI_LimitStrength + UCI_Elo: caps engine to a target Elo (1320..3190)

We expose both, prioritising UCI_Elo when set. A fresh engine instance is
spawned per request (cheap; engine cleanup happens on session end).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import chess
import chess.engine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import PositionSession, PositionSessionMove
from app.models.position_session import PositionSessionStatus

logger = logging.getLogger(__name__)


MIN_UCI_ELO = 1320
MAX_UCI_ELO = 3190


def _clamp_elo(elo: int | None) -> int | None:
    if elo is None:
        return None
    return max(MIN_UCI_ELO, min(MAX_UCI_ELO, elo))


async def _spawn_engine_with_strength(
    skill_level: int, sf_elo: int | None
) -> tuple[chess.engine.UciProtocol, object]:
    """Returns (engine, transport). Caller must engine.quit() when done."""
    settings = get_settings()
    transport, engine = await chess.engine.popen_uci(str(settings.stockfish_abs_path))
    config: dict[str, int | bool] = {
        "Threads": max(1, settings.stockfish_threads // 2),
        "Hash": max(64, settings.stockfish_hash_mb // 2),
        "Skill Level": max(0, min(20, int(skill_level))),
    }
    if sf_elo is not None:
        config["UCI_LimitStrength"] = True
        config["UCI_Elo"] = _clamp_elo(sf_elo)
    await engine.configure(config)
    return engine, transport


def _result_status(board: chess.Board, user_is_white: bool) -> tuple[PositionSessionStatus, str]:
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return PositionSessionStatus.ACTIVE, ""
    reason = outcome.termination.name.lower()
    if outcome.winner is None:
        return PositionSessionStatus.DRAW, reason
    if (outcome.winner == chess.WHITE) == user_is_white:
        return PositionSessionStatus.USER_WON, reason
    return PositionSessionStatus.USER_LOST, reason


async def _persist_move(
    session: AsyncSession,
    sess: PositionSession,
    move: chess.Move,
    fen_after: str,
    is_user: bool,
    eval_cp: int | None,
    eval_mate: int | None,
) -> None:
    board = chess.Board(sess.current_fen)
    try:
        san = board.san(move)
    except Exception:
        san = move.uci()
    sess.final_ply += 1
    session.add(PositionSessionMove(
        session_id=sess.id,
        ply=sess.final_ply,
        is_user=is_user,
        uci=move.uci(),
        san=san,
        fen_after=fen_after,
        eval_cp_after=eval_cp,
        eval_mate_after=eval_mate,
    ))
    sess.current_fen = fen_after


@dataclass
class EngineMoveResult:
    user_status: PositionSessionStatus
    engine_uci: str | None
    engine_san: str | None
    fen_after: str
    eval_cp: int | None
    eval_mate: int | None
    reason: str | None


async def start_session(
    session: AsyncSession,
    starting_fen: str,
    user_color: str,
    *,
    skill_level: int = 10,
    sf_elo: int | None = None,
    depth: int = 12,
    title: str | None = None,
    source: str | None = None,
    source_ref: dict | None = None,
    player_id: int | None = None,
) -> PositionSession:
    board = chess.Board(starting_fen)
    if not board.is_valid():
        raise ValueError("Invalid FEN")
    if user_color not in ("white", "black"):
        raise ValueError("user_color must be 'white' or 'black'")

    sess = PositionSession(
        player_id=player_id,
        title=title,
        starting_fen=starting_fen,
        current_fen=starting_fen,
        user_color=user_color,
        sf_skill_level=skill_level,
        sf_elo=sf_elo,
        sf_depth=depth,
        source=source,
        source_ref=source_ref,
    )
    session.add(sess)
    await session.flush()

    # If it's not the user's turn first, play engine's opening move now
    side_to_move_is_white = board.turn == chess.WHITE
    user_is_white = user_color == "white"
    if side_to_move_is_white != user_is_white:
        await _play_engine_turn(session, sess)
    await session.commit()
    return sess


async def _play_engine_turn(
    session: AsyncSession, sess: PositionSession
) -> EngineMoveResult:
    board = chess.Board(sess.current_fen)
    user_is_white = sess.user_color == "white"

    engine, transport = await _spawn_engine_with_strength(
        sess.sf_skill_level, sess.sf_elo
    )
    try:
        play = await engine.play(
            board,
            chess.engine.Limit(depth=sess.sf_depth),
            info=chess.engine.INFO_SCORE,
        )
        engine_move = play.move
        score = play.info.get("score") if play.info else None
    finally:
        try:
            await engine.quit()
        except Exception:
            pass

    if engine_move is None:
        status, reason = _result_status(board, user_is_white)
        sess.status = status
        sess.result_reason = reason
        sess.ended_at = datetime.now(timezone.utc)
        return EngineMoveResult(
            user_status=status, engine_uci=None, engine_san=None,
            fen_after=sess.current_fen, eval_cp=None, eval_mate=None, reason=reason,
        )

    board_after = board.copy()
    san = board.san(engine_move)
    board_after.push(engine_move)

    eval_cp = eval_mate = None
    if score is not None:
        s = score.pov(chess.WHITE if user_is_white else chess.BLACK)
        if s.is_mate():
            eval_mate = s.mate()
        else:
            eval_cp = s.score(mate_score=100_000)

    await _persist_move(
        session, sess, engine_move, board_after.fen(),
        is_user=False, eval_cp=eval_cp, eval_mate=eval_mate,
    )

    status, reason = _result_status(board_after, user_is_white)
    if status != PositionSessionStatus.ACTIVE:
        sess.status = status
        sess.result_reason = reason
        sess.ended_at = datetime.now(timezone.utc)

    return EngineMoveResult(
        user_status=status, engine_uci=engine_move.uci(), engine_san=san,
        fen_after=board_after.fen(), eval_cp=eval_cp, eval_mate=eval_mate,
        reason=reason,
    )


@dataclass
class UserMoveResult:
    accepted: bool
    error: str | None
    new_fen: str
    status: PositionSessionStatus
    engine_uci: str | None = None
    engine_san: str | None = None
    eval_cp: int | None = None
    eval_mate: int | None = None
    user_uci: str | None = None
    user_san: str | None = None


async def apply_user_move(
    session: AsyncSession, sess: PositionSession, move_input: str
) -> UserMoveResult:
    if sess.status != PositionSessionStatus.ACTIVE:
        return UserMoveResult(
            accepted=False, error=f"session not active (status={sess.status})",
            new_fen=sess.current_fen, status=sess.status,
        )

    board = chess.Board(sess.current_fen)
    user_is_white = sess.user_color == "white"
    if (board.turn == chess.WHITE) != user_is_white:
        return UserMoveResult(
            accepted=False, error="not your turn",
            new_fen=sess.current_fen, status=sess.status,
        )

    move_input = (move_input or "").strip()
    user_move: chess.Move | None = None
    try:
        user_move = board.parse_san(move_input)
    except (ValueError, chess.InvalidMoveError):
        try:
            user_move = chess.Move.from_uci(move_input)
            if user_move not in board.legal_moves:
                user_move = None
        except (ValueError, chess.InvalidMoveError):
            user_move = None

    if user_move is None:
        return UserMoveResult(
            accepted=False, error="illegal or unparseable move",
            new_fen=sess.current_fen, status=sess.status,
        )

    user_san = board.san(user_move)
    board.push(user_move)
    await _persist_move(
        session, sess, user_move, board.fen(),
        is_user=True, eval_cp=None, eval_mate=None,
    )

    status, reason = _result_status(board, user_is_white)
    if status != PositionSessionStatus.ACTIVE:
        sess.status = status
        sess.result_reason = reason
        sess.ended_at = datetime.now(timezone.utc)
        await session.commit()
        return UserMoveResult(
            accepted=True, error=None, new_fen=board.fen(), status=status,
            user_uci=user_move.uci(), user_san=user_san,
        )

    # Engine response
    eng_result = await _play_engine_turn(session, sess)
    await session.commit()
    return UserMoveResult(
        accepted=True, error=None,
        new_fen=sess.current_fen, status=eng_result.user_status,
        engine_uci=eng_result.engine_uci, engine_san=eng_result.engine_san,
        eval_cp=eng_result.eval_cp, eval_mate=eng_result.eval_mate,
        user_uci=user_move.uci(), user_san=user_san,
    )


async def abandon_session(session: AsyncSession, sess: PositionSession) -> None:
    if sess.status == PositionSessionStatus.ACTIVE:
        sess.status = PositionSessionStatus.ABANDONED
        sess.ended_at = datetime.now(timezone.utc)
        await session.commit()

"""Play-out-a-position service: user vs Stockfish from any starting FEN.

Stockfish strength is controlled via two UCI options:
  - Skill Level (0..20): coarse strength reduction
  - UCI_LimitStrength + UCI_Elo: caps engine to a target Elo (1320..3190)

We expose both, prioritising UCI_Elo when set. A fresh engine instance is
spawned per request (cheap; engine cleanup happens on session end).
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import chess
import chess.engine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import PositionSession, PositionSessionMove
from app.models.position_session import PositionSessionStatus
from app.services import opening_trainer as ot

logger = logging.getLogger(__name__)


MIN_UCI_ELO = 1320
MAX_UCI_ELO = 3190


def _clamp_elo(elo: int | None) -> int | None:
    if elo is None:
        return None
    return max(MIN_UCI_ELO, min(MAX_UCI_ELO, elo))


def _spawn_engine_sync(
    skill_level: int, sf_elo: int | None
) -> chess.engine.SimpleEngine:
    """Sync version using SimpleEngine.popen_uci.

    Uses regular subprocess.Popen which works on any event loop. This is
    needed because Windows uvicorn often runs on SelectorEventLoop which
    doesn't support asyncio.subprocess_exec.
    """
    settings = get_settings()
    eng = chess.engine.SimpleEngine.popen_uci(str(settings.stockfish_abs_path))
    config: dict[str, int | bool] = {
        "Threads": max(1, settings.stockfish_threads // 2),
        "Hash": max(64, settings.stockfish_hash_mb // 2),
        "Skill Level": max(0, min(20, int(skill_level))),
    }
    if sf_elo is not None:
        config["UCI_LimitStrength"] = True
        config["UCI_Elo"] = _clamp_elo(sf_elo)
    eng.configure(config)
    return eng


async def _spawn_engine_with_strength(
    skill_level: int, sf_elo: int | None
) -> tuple[chess.engine.SimpleEngine, None]:
    """Async wrapper that spawns the engine in a thread to avoid event-loop issues."""
    import asyncio
    eng = await asyncio.to_thread(_spawn_engine_sync, skill_level, sf_elo)
    return eng, None


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


def _pick_opening_line(opening_key: str) -> tuple[ot.TrainerOpening, str | None, list[ot.TrainerMove]]:
    """Resolve an opening into a concrete sequence of moves.

    Returns (opening, branch_label_or_None_for_mainline, flat_moves).
    Picks randomly between the mainline and any registered branches so the
    user has to adapt each session.
    """
    op = ot.get_opening(opening_key)
    if op is None:
        raise ValueError(f"unknown opening: {opening_key}")
    if op.branches:
        pick_idx = random.randint(0, len(op.branches))  # 0 = mainline
        if pick_idx == 0:
            return op, None, list(op.moves)
        branch = op.branches[pick_idx - 1]
        return op, branch.label, ot.materialize_branch(op, branch)
    return op, None, list(op.moves)


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
    max_undos: int = 0,
    opening_key: str | None = None,
    simulation_moves: list[dict] | None = None,
) -> PositionSession:
    # Opening-constrained sessions always start from the standard initial
    # position (the opening library is built against it) — we ignore the
    # passed FEN to keep things consistent.
    opening_branch_label: str | None = None
    opening_moves_data: list[dict] | None = None
    opening_status: str | None = None
    # Simulation mode: forced engine moves but NO deviation penalty for user
    if simulation_moves:
        opening_moves_data = simulation_moves
        opening_status = "opp_simulation"
    if opening_key:
        op, opening_branch_label, flat = _pick_opening_line(opening_key)
        starting_fen = op.starting_fen
        if user_color != op.user_color:
            user_color = op.user_color
        opening_moves_data = [
            {"uci": m.uci, "san": m.san, "color": m.color}
            for m in flat
        ]
        opening_status = "in_book"

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
        max_undos=max(0, max_undos),
        undos_used=0,
        opening_key=opening_key,
        opening_branch_label=opening_branch_label,
        opening_moves=opening_moves_data,
        opening_ply_index=0,
        opening_status=opening_status,
    )
    session.add(sess)
    await session.flush()

    # If it's not the user's turn first, play engine's opening move now.
    # In opening-constrained mode this will use the prescribed move.
    side_to_move_is_white = board.turn == chess.WHITE
    user_is_white = user_color == "white"
    if side_to_move_is_white != user_is_white:
        await _play_engine_turn(session, sess)
    await session.commit()
    return sess


def _next_opening_move(sess: PositionSession) -> dict | None:
    """Return the next prescribed move dict, or None if past the line.

    Also self-heals: if the actual number of plies played on the board has
    already exceeded the prescribed line length, the session is forced into
    the "completed" state — this catches stale sessions corrupted by an
    earlier undo bug that left status="in_book" after the endgame had
    started.
    """
    if not sess.opening_moves:
        return None
    if sess.opening_status not in ("in_book", "opp_simulation"):
        return None
    if (sess.final_ply or 0) >= len(sess.opening_moves):
        sess.opening_status = "completed"
        return None
    if sess.opening_ply_index >= len(sess.opening_moves):
        sess.opening_status = "completed"
        return None
    return sess.opening_moves[sess.opening_ply_index]


def _advance_opening(sess: PositionSession) -> None:
    sess.opening_ply_index = (sess.opening_ply_index or 0) + 1
    if sess.opening_moves and sess.opening_ply_index >= len(sess.opening_moves):
        sess.opening_status = "completed"


async def _play_engine_turn(
    session: AsyncSession, sess: PositionSession
) -> EngineMoveResult:
    board = chess.Board(sess.current_fen)
    user_is_white = sess.user_color == "white"

    # If we're still in the constrained opening AND the next prescribed move
    # belongs to the engine, play that move directly instead of asking SF.
    forced_move: chess.Move | None = None
    forced = _next_opening_move(sess)
    if forced is not None and forced.get("uci"):
        expected_color = forced["color"]
        engine_color = "black" if user_is_white else "white"
        if expected_color == engine_color:
            try:
                mv = chess.Move.from_uci(forced["uci"])
                if mv in board.legal_moves:
                    forced_move = mv
            except Exception:
                logger.warning("opening prescribed engine move illegal: %s", forced)

    import asyncio
    if forced_move is not None:
        engine_move = forced_move
        score = None
        _advance_opening(sess)
    else:
        # In opp_simulation mode we still want to bump the cursor for this
        # engine ply (the script has ended; SF takes over).
        if sess.opening_status == "opp_simulation" and forced is not None:
            _advance_opening(sess)
        engine, _ = await _spawn_engine_with_strength(
            sess.sf_skill_level, sess.sf_elo
        )
        try:
            play = await asyncio.to_thread(
                engine.play,
                board,
                chess.engine.Limit(depth=sess.sf_depth),
                info=chess.engine.INFO_SCORE,
            )
            engine_move = play.move
            score = play.info.get("score") if play.info else None
        finally:
            try:
                await asyncio.to_thread(engine.quit)
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
    user_captured: str | None = None     # piece type captured by user: 'p','n','b','r','q'
    engine_captured: str | None = None
    in_check_after_user: bool = False     # opponent in check after user's move
    in_check_after_engine: bool = False   # user in check after engine's reply
    best_user_uci: str | None = None
    best_user_san: str | None = None
    user_cp_loss: int | None = None
    user_quality: str | None = None       # best/good/inaccuracy/mistake/blunder


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

    # Opening enforcement: if we're still in book, the user must play the
    # prescribed move. Otherwise either auto-undo (consumes 1 from the budget)
    # or lose the session outright.
    # In opp_simulation mode the engine has a script but the USER plays freely.
    next_op = _next_opening_move(sess)
    if next_op is not None and sess.opening_status == "in_book":
        user_color_str = "white" if board.turn == chess.WHITE else "black"
        if next_op["color"] == user_color_str:
            if user_move.uci() != next_op["uci"]:
                expected_san = next_op["san"]
                expected_uci = next_op["uci"]
                remaining = max(0, (sess.max_undos or 0) - (sess.undos_used or 0))
                if remaining > 0:
                    sess.undos_used = (sess.undos_used or 0) + 1
                    await session.commit()
                    return UserMoveResult(
                        accepted=False,
                        error=(
                            f"Hors théorie : on attend {expected_san}. "
                            f"Annulation auto consommée ({remaining - 1} restantes)."
                        ),
                        new_fen=sess.current_fen, status=sess.status,
                        best_user_uci=expected_uci, best_user_san=expected_san,
                    )
                # No undos left → instant loss.
                sess.status = PositionSessionStatus.USER_LOST
                sess.result_reason = "opening_deviation"
                sess.ended_at = datetime.now(timezone.utc)
                await session.commit()
                return UserMoveResult(
                    accepted=False,
                    error=(
                        f"Défaite : hors théorie ({expected_san} attendu) et plus d'annulation."
                    ),
                    new_fen=sess.current_fen, status=sess.status,
                    best_user_uci=expected_uci, best_user_san=expected_san,
                )

    # Detect what the user captures (if any)
    user_captured = None
    if board.is_capture(user_move):
        if board.is_en_passant(user_move):
            user_captured = "p"
        else:
            captured_piece = board.piece_at(user_move.to_square)
            if captured_piece is not None:
                user_captured = chess.PIECE_SYMBOLS[captured_piece.piece_type]

    # Pre-compute Stockfish's preferred move + cp for quality grading
    best_user_uci = best_user_san = None
    user_cp_loss = None
    user_quality = None
    try:
        import asyncio
        analysis_engine, _ = await _spawn_engine_with_strength(20, None)
        try:
            analysis = await asyncio.to_thread(
                analysis_engine.analyse, board, chess.engine.Limit(depth=12),
            )
            best_pv = analysis.get("pv") if isinstance(analysis, dict) else None
            best_move = best_pv[0] if best_pv else None
            if best_move is not None:
                best_user_uci = best_move.uci()
                best_user_san = board.san(best_move)
            best_score = analysis.get("score")
            # Now eval the user's actual move
            test_board = board.copy()
            test_board.push(user_move)
            after_user = await asyncio.to_thread(
                analysis_engine.analyse, test_board, chess.engine.Limit(depth=12),
            )
            after_score = after_user.get("score") if isinstance(after_user, dict) else None
            if best_score is not None and after_score is not None:
                best_cp = best_score.pov(board.turn).score(mate_score=100_000)
                # after_score is from opponent's POV, flip to user
                user_cp = -after_score.pov(board.turn).score(mate_score=100_000)
                if best_cp is not None and user_cp is not None:
                    user_cp_loss = max(0, best_cp - user_cp)
                    if user_move == best_move:
                        user_quality = "best"
                    elif user_cp_loss < 30:
                        user_quality = "excellent"
                    elif user_cp_loss < 80:
                        user_quality = "good"
                    elif user_cp_loss < 150:
                        user_quality = "inaccuracy"
                    elif user_cp_loss < 300:
                        user_quality = "mistake"
                    else:
                        user_quality = "blunder"
        finally:
            try:
                await asyncio.to_thread(analysis_engine.quit)
            except Exception:
                pass
    except Exception:
        logger.warning("user move quality analysis failed", exc_info=True)

    user_san = board.san(user_move)
    board.push(user_move)
    in_check_after_user = board.is_check()
    await _persist_move(
        session, sess, user_move, board.fen(),
        is_user=True, eval_cp=None, eval_mate=None,
    )

    # Advance the prescribed-move cursor:
    #  - in_book : only if the user played the exact prescribed move
    #  - opp_simulation : always (the script tracks engine moves, but the
    #    cursor must move past every ply to stay aligned with the board)
    if next_op is not None:
        if sess.opening_status == "opp_simulation":
            _advance_opening(sess)
        elif next_op["uci"] == user_move.uci():
            _advance_opening(sess)

    status, reason = _result_status(board, user_is_white)
    if status != PositionSessionStatus.ACTIVE:
        sess.status = status
        sess.result_reason = reason
        sess.ended_at = datetime.now(timezone.utc)
        await session.commit()
        return UserMoveResult(
            accepted=True, error=None, new_fen=board.fen(), status=status,
            user_uci=user_move.uci(), user_san=user_san,
            user_captured=user_captured,
            in_check_after_user=in_check_after_user,
            best_user_uci=best_user_uci, best_user_san=best_user_san,
            user_cp_loss=user_cp_loss, user_quality=user_quality,
        )

    # Engine response — detect what engine captures
    pre_engine_board = chess.Board(sess.current_fen)
    eng_result = await _play_engine_turn(session, sess)
    engine_captured = None
    in_check_after_engine = False
    if eng_result.engine_uci:
        try:
            em = chess.Move.from_uci(eng_result.engine_uci)
            if pre_engine_board.is_capture(em):
                if pre_engine_board.is_en_passant(em):
                    engine_captured = "p"
                else:
                    cp = pre_engine_board.piece_at(em.to_square)
                    if cp is not None:
                        engine_captured = chess.PIECE_SYMBOLS[cp.piece_type]
            final_board = chess.Board(eng_result.fen_after)
            in_check_after_engine = final_board.is_check()
        except Exception:
            pass

    await session.commit()
    return UserMoveResult(
        accepted=True, error=None,
        new_fen=sess.current_fen, status=eng_result.user_status,
        engine_uci=eng_result.engine_uci, engine_san=eng_result.engine_san,
        eval_cp=eng_result.eval_cp, eval_mate=eng_result.eval_mate,
        user_uci=user_move.uci(), user_san=user_san,
        user_captured=user_captured, engine_captured=engine_captured,
        in_check_after_user=in_check_after_user,
        in_check_after_engine=in_check_after_engine,
        best_user_uci=best_user_uci, best_user_san=best_user_san,
        user_cp_loss=user_cp_loss, user_quality=user_quality,
    )


async def abandon_session(session: AsyncSession, sess: PositionSession) -> None:
    if sess.status == PositionSessionStatus.ACTIVE:
        sess.status = PositionSessionStatus.ABANDONED
        sess.ended_at = datetime.now(timezone.utc)
        await session.commit()


@dataclass
class UndoResult:
    accepted: bool
    error: str | None
    current_fen: str
    undos_used: int
    undos_remaining: int
    plies_popped: int


async def undo_last_user_move(
    session: AsyncSession, sess: PositionSession
) -> UndoResult:
    """Pop the last (user, engine) move pair from the session.

    Restores the board to the position the user faced just before her last
    move — so she can try a different one. Consumes 1 undo from the budget.
    Refuses if no undos remaining, no moves played yet, or session not active.
    """
    if sess.status != PositionSessionStatus.ACTIVE:
        return UndoResult(False, "Session non active.", sess.current_fen,
                          sess.undos_used, max(0, sess.max_undos - sess.undos_used), 0)
    remaining = max(0, sess.max_undos - (sess.undos_used or 0))
    if remaining <= 0:
        return UndoResult(False, "Aucune annulation restante.", sess.current_fen,
                          sess.undos_used, 0, 0)

    moves = list((await session.execute(
        select(PositionSessionMove)
        .where(PositionSessionMove.session_id == sess.id)
        .order_by(PositionSessionMove.ply.desc())
    )).scalars())

    if not moves:
        return UndoResult(False, "Aucun coup à annuler.", sess.current_fen,
                          sess.undos_used, remaining, 0)

    # Identify the moves to remove: the last user move + the engine reply that
    # came after (if any). The list is sorted desc by ply.
    to_delete: list[PositionSessionMove] = []
    # If the most recent move is engine, drop it together with the prior user move.
    if not moves[0].is_user and len(moves) >= 2 and moves[1].is_user:
        to_delete = [moves[0], moves[1]]
    elif moves[0].is_user:
        # Last persisted move is the user's; drop just that one.
        to_delete = [moves[0]]
    else:
        # Engine-only at top with no user move underneath — should not happen,
        # but bail gracefully.
        return UndoResult(False, "Etat de session incoherent.", sess.current_fen,
                          sess.undos_used, remaining, 0)

    deleted_ids = {mv.id for mv in to_delete}
    for mv in to_delete:
        await session.delete(mv)
    # Without explicit flush + autoflush=False, the next SELECT can still
    # see the rows pending deletion; flush forces the DB-level removal so
    # the leftover query is authoritative.
    await session.flush()

    leftover = list((await session.execute(
        select(PositionSessionMove)
        .where(PositionSessionMove.session_id == sess.id)
        .where(PositionSessionMove.id.notin_(deleted_ids) if deleted_ids else True)
        .order_by(PositionSessionMove.ply.desc())
        .limit(1)
    )).scalars())
    new_fen = leftover[0].fen_after if leftover else sess.starting_fen
    sess.current_fen = new_fen
    sess.final_ply = max(0, sess.final_ply - len(to_delete))
    sess.undos_used = (sess.undos_used or 0) + 1

    # In opening-constrained mode, rewind the prescribed-line cursor only
    # while we are STILL inside the opening (status == "in_book"). Once the
    # line was completed, undos during the middlegame/endgame must NOT
    # re-trigger opening enforcement — only the move pointer (purely
    # informational at that point) is rolled back.
    if sess.opening_status == "in_book" and sess.opening_moves:
        sess.opening_ply_index = max(0, (sess.opening_ply_index or 0) - len(to_delete))
    elif sess.opening_status == "completed" and sess.opening_moves:
        # Keep the counter capped at the line length so the UI keeps showing
        # "✓ Ligne complétée" instead of suddenly rewinding back into theory.
        sess.opening_ply_index = max(
            len(sess.opening_moves),
            (sess.opening_ply_index or 0) - len(to_delete),
        )

    await session.commit()
    return UndoResult(
        accepted=True, error=None,
        current_fen=new_fen,
        undos_used=sess.undos_used,
        undos_remaining=max(0, sess.max_undos - sess.undos_used),
        plies_popped=len(to_delete),
    )

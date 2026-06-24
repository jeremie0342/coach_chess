"""Stockfish-driven move analyzer.

For each move in a game, we compute:
  - Pre-move evaluation (from side-to-move's POV)
  - Stockfish's best move + PV from that position
  - Post-move evaluation
  - cp_loss = how many centipawns the player gave up vs. the best move
  - Quality classification

Centipawn loss formula:
  cp_loss = score_player_pov(fen_before) - (-score(fen_after))
         = score(fen_before) + score(fen_after)
  where both scores are from each position's side-to-move POV.

Quality thresholds (Lichess-style):
  best        : cp_loss <= 10
  excellent   : cp_loss <= 30
  good        : cp_loss <= 60
  inaccuracy  : 60 < cp_loss <= 150
  mistake     : 150 < cp_loss <= 300
  blunder     : cp_loss > 300
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import chess
import chess.engine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Game, Move, MoveAnalysis
from app.models.analysis import MoveQuality

logger = logging.getLogger(__name__)

MATE_VALUE = 100_000


@dataclass
class GameAnalysisStats:
    game_id: int
    moves_analyzed: int = 0
    blunders: int = 0
    mistakes: int = 0
    inaccuracies: int = 0
    elapsed_s: float = 0.0


def classify(cp_loss: int | None) -> MoveQuality:
    if cp_loss is None:
        return MoveQuality.GOOD
    if cp_loss <= 10:
        return MoveQuality.BEST
    if cp_loss <= 30:
        return MoveQuality.EXCELLENT
    if cp_loss <= 60:
        return MoveQuality.GOOD
    if cp_loss <= 150:
        return MoveQuality.INACCURACY
    if cp_loss <= 300:
        return MoveQuality.MISTAKE
    return MoveQuality.BLUNDER


def _score_to_cp(score: chess.engine.PovScore, pov: chess.Color) -> tuple[int | None, int | None]:
    """Return (eval_cp, eval_mate) from `pov`'s perspective."""
    s = score.pov(pov)
    if s.is_mate():
        return None, s.mate()
    return s.score(mate_score=MATE_VALUE), None


def _to_player_cp(eval_cp: int | None, eval_mate: int | None) -> int:
    """Collapse cp / mate into a signed centipawn value for arithmetic."""
    if eval_mate is not None:
        # Mate-in-N: clamp at +/- 30000 (so blunder math doesn't explode)
        return 30_000 if eval_mate > 0 else -30_000
    return eval_cp or 0


async def analyze_game(
    session: AsyncSession,
    game: Game,
    engine: chess.engine.SimpleEngine,
    depth: int | None = None,
    skip_book_plies: int = 8,
    multipv: int = 1,
    force: bool = False,
    commit_every: int = 10,
) -> GameAnalysisStats:
    """Analyze all moves of one game. Skips first `skip_book_plies` (pure opening).

    Idempotent: if force=False, existing analyses are skipped per-move.
    """
    settings = get_settings()
    depth = depth or settings.stockfish_default_depth
    started = time.perf_counter()
    stats = GameAnalysisStats(game_id=game.id)

    moves_q = await session.execute(
        select(Move).where(Move.game_id == game.id).order_by(Move.ply)
    )
    moves = list(moves_q.scalars())
    if not moves:
        return stats

    # Pre-load existing analyses to know what to skip
    existing_q = await session.execute(
        select(MoveAnalysis).where(MoveAnalysis.move_id.in_([m.id for m in moves]))
    )
    existing_by_move = {a.move_id: a for a in existing_q.scalars()}

    # We cache eval_cp(fen) so each unique position is analyzed once
    eval_cache: dict[str, tuple[int | None, int | None, str | None, str | None, list[str]]] = {}

    async def evaluate(fen: str) -> tuple[int | None, int | None, str | None, str | None, list[str]]:
        if fen in eval_cache:
            return eval_cache[fen]
        board = chess.Board(fen)
        import asyncio
        from app.services.stockfish import _engine_lock
        async with _engine_lock:
            info = await asyncio.to_thread(
                engine.analyse,
                board,
                chess.engine.Limit(depth=depth),
                multipv=multipv,
            )
        if isinstance(info, dict):
            info = [info]
        first = info[0]
        eval_cp, eval_mate = _score_to_cp(first["score"], board.turn)
        pv = first.get("pv") or []
        best_uci = pv[0].uci() if pv else None
        try:
            best_san = board.san(pv[0]) if pv else None
        except Exception:
            best_san = None
        pv_uci = [m.uci() for m in pv]
        eval_cache[fen] = (eval_cp, eval_mate, best_uci, best_san, pv_uci)
        return eval_cache[fen]

    for m in moves:
        if not force and m.id in existing_by_move:
            continue
        # Skip pure book (opening): the first few plies are theory, not blunders.
        if m.ply <= skip_book_plies:
            ma = MoveAnalysis(
                move_id=m.id,
                depth=0,
                quality=MoveQuality.BOOK,
            )
            session.add(ma)
            stats.moves_analyzed += 1
            continue

        eval_b_cp, eval_b_mate, best_uci, best_san, pv_uci = await evaluate(m.fen_before)
        eval_a_cp, eval_a_mate, _, _, _ = await evaluate(m.fen_after)

        # Both from side-to-move POV at each position.
        # Player POV: from m.fen_before, side to move is the player.
        player_pov_before = _to_player_cp(eval_b_cp, eval_b_mate)
        opp_pov_after = _to_player_cp(eval_a_cp, eval_a_mate)
        # After the move, side to move flipped. So from PLAYER POV, eval_after = -opp_pov_after.
        player_pov_after = -opp_pov_after
        cp_loss = max(0, player_pov_before - player_pov_after)

        # If the played move equals the best move, force cp_loss = 0
        if best_uci and m.uci == best_uci:
            cp_loss = 0

        quality = classify(cp_loss)
        if quality == MoveQuality.BLUNDER:
            stats.blunders += 1
        elif quality == MoveQuality.MISTAKE:
            stats.mistakes += 1
        elif quality == MoveQuality.INACCURACY:
            stats.inaccuracies += 1

        # Tactical theme classification on the player's significant misses
        tags: list[str] | None = None
        if quality in (MoveQuality.BLUNDER, MoveQuality.MISTAKE, MoveQuality.INACCURACY):
            from app.services.tactical_themes import ClassifyInput, classify_themes
            tags = classify_themes(ClassifyInput(
                fen_before=m.fen_before,
                played_uci=m.uci,
                best_uci=best_uci,
                pv_uci=pv_uci,
                eval_cp_before=eval_b_cp,
                eval_mate_before=eval_b_mate,
            )) or None

        ma = MoveAnalysis(
            move_id=m.id,
            depth=depth,
            eval_cp=eval_a_cp,
            eval_mate=eval_a_mate,
            eval_cp_before=eval_b_cp,
            eval_mate_before=eval_b_mate,
            cp_loss=cp_loss,
            quality=quality,
            best_move_uci=best_uci,
            best_move_san=best_san,
            pv=pv_uci,
            tags=tags,
        )
        session.add(ma)
        stats.moves_analyzed += 1

        # Periodic commit so a Ctrl+C doesn't lose the moves we already crunched.
        if commit_every and stats.moves_analyzed % commit_every == 0:
            await session.commit()

    game.analysis_status = "done"
    from datetime import datetime, timezone
    game.analyzed_at = datetime.now(timezone.utc)
    await session.commit()

    stats.elapsed_s = time.perf_counter() - started
    logger.info(
        "analyzed game id=%d moves=%d blunders=%d mistakes=%d inacc=%d in %.1fs",
        game.id, stats.moves_analyzed, stats.blunders, stats.mistakes,
        stats.inaccuracies, stats.elapsed_s,
    )
    return stats

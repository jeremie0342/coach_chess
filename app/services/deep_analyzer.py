"""Re-analyze critical (blunder/mistake) positions at high Stockfish depth.

Standard analysis runs at depth 20. We pick the worst N moves of the user
(by cp_loss) and re-run Stockfish on their fen_before at depth 28 (default).

Results land in MoveAnalysis.deep_* columns; the original depth-20 fields
stay untouched (so puzzle generation and quality classification still use
the cheaper data unless explicitly switched to deep).

We use the shared Stockfish engine (get_engine) so concurrent runs are
serialized. Run via the worker for batch jobs.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import chess
import chess.engine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, MoveAnalysis, Player
from app.models.analysis import MoveQuality
from app.services.stockfish import get_engine

logger = logging.getLogger(__name__)


@dataclass
class DeepRunStats:
    moves_deep_analyzed: int = 0
    skipped_existing: int = 0
    elapsed_s: float = 0.0


def _score_to_cp(score: chess.engine.PovScore, pov: chess.Color) -> tuple[int | None, int | None]:
    s = score.pov(pov)
    if s.is_mate():
        return None, s.mate()
    return s.score(mate_score=100_000), None


async def _deep_one(
    session: AsyncSession,
    analysis: MoveAnalysis,
    move: Move,
    engine: chess.engine.UciProtocol,
    depth: int,
    multipv: int = 1,
) -> bool:
    """Re-analyze move.fen_before; store in deep_* fields. True if updated."""
    board = chess.Board(move.fen_before)
    info = await engine.analyse(
        board, chess.engine.Limit(depth=depth), multipv=multipv
    )
    if isinstance(info, dict):
        info = [info]
    first = info[0]
    eval_cp, eval_mate = _score_to_cp(first["score"], board.turn)
    pv = first.get("pv") or []
    best_uci = pv[0].uci() if pv else None
    best_san = None
    if pv:
        try:
            best_san = board.san(pv[0])
        except Exception:
            best_san = None
    pv_uci = [m.uci() for m in pv]

    analysis.deep_depth = depth
    analysis.deep_eval_cp = eval_cp
    analysis.deep_eval_mate = eval_mate
    analysis.deep_best_uci = best_uci
    analysis.deep_best_san = best_san
    analysis.deep_pv = pv_uci
    return True


async def deep_analyze_critical(
    session: AsyncSession,
    player: Player | None = None,
    limit: int = 50,
    depth: int = 28,
    min_cp_loss: int = 150,
    force: bool = False,
    commit_every: int = 5,
) -> DeepRunStats:
    """Re-analyze the player's worst N moves at high depth.

    If `player` is None, runs across all is_me=True player(s) — typically just one.
    """
    started = time.perf_counter()
    stats = DeepRunStats()

    if player is None:
        player = (await session.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalar_one_or_none()
        if not player:
            return stats

    from sqlalchemy import case, or_
    my_is_white = case(
        (Game.white_player_id == player.id, True),
        else_=False,
    )

    q = (
        select(MoveAnalysis, Move)
        .join(Move, Move.id == MoveAnalysis.move_id)
        .join(Game, Game.id == Move.game_id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Move.is_white == my_is_white)
        .where(MoveAnalysis.quality.in_((MoveQuality.BLUNDER, MoveQuality.MISTAKE)))
        .where(MoveAnalysis.cp_loss >= min_cp_loss)
    )
    if not force:
        q = q.where(MoveAnalysis.deep_depth.is_(None))
    q = q.order_by(MoveAnalysis.cp_loss.desc().nullslast()).limit(limit)

    rows = list((await session.execute(q)).all())
    if not rows:
        stats.elapsed_s = time.perf_counter() - started
        return stats

    engine = await get_engine()

    for analysis, move in rows:
        if not force and analysis.deep_depth is not None:
            stats.skipped_existing += 1
            continue
        await _deep_one(session, analysis, move, engine, depth=depth)
        stats.moves_deep_analyzed += 1
        if commit_every and stats.moves_deep_analyzed % commit_every == 0:
            await session.commit()

    await session.commit()
    stats.elapsed_s = time.perf_counter() - started
    logger.info(
        "deep_analyze player=%s deep=%d skipped=%d in %.1fs (depth=%d)",
        player.chesscom_username, stats.moves_deep_analyzed, stats.skipped_existing,
        stats.elapsed_s, depth,
    )
    return stats

"""Export an annotated PGN of one of the user's games.

We rebuild the game tree from our stored Move rows (not the raw PGN string),
so we control comments and NAGs cleanly. Output is standard PGN that
Lichess, ChessBase and most viewers parse.

Annotations attached:
  - Standard NAGs after each move quality: 1 (!), 2 (?), 3 (!!), 4 (??), 5 (!?), 6 (?!)
  - `{[%eval 1.23]}` Lichess-style score in pawns (or `[%eval #N]` for mate)
  - For mistakes/blunders: `(better was Nf3)` inline
  - For the worst N moves: a coach comment from the LLM cache (optional)
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PROJECT_ROOT
from app.models import Game, Move, MoveAnalysis, Opening
from app.models.analysis import MoveQuality
from app.services.coach.explainer import explain_move

logger = logging.getLogger(__name__)


# Standard PGN NAG codes
NAG_BY_QUALITY = {
    MoveQuality.BLUNDER: 4,
    MoveQuality.MISTAKE: 2,
    MoveQuality.INACCURACY: 6,        # ?!
    MoveQuality.EXCELLENT: 1,         # !
    MoveQuality.BEST: 1,
    MoveQuality.BRILLIANT: 3,         # !!
    MoveQuality.GREAT: 3,
}


COACH_CACHE_DIR = PROJECT_ROOT / "data" / "coach_cache"


def _eval_comment(eval_cp: int | None, eval_mate: int | None) -> str | None:
    if eval_mate is not None:
        return f"[%eval #{eval_mate}]"
    if eval_cp is None:
        return None
    if abs(eval_cp) >= 30000:
        return None
    return f"[%eval {eval_cp / 100:.2f}]"


def _cached_llm_comment(fen_before: str, played_uci: str, best_uci: str | None) -> str | None:
    key = f"{fen_before}|{played_uci}|{best_uci or ''}"
    h = hashlib.sha1(key.encode()).hexdigest()[:24]
    path = COACH_CACHE_DIR / f"{h}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("explanation") or "").strip() or None
    except Exception:
        return None


@dataclass
class ExportOptions:
    include_llm: bool = False          # only effective if cache hits exist
    llm_only_worst: int = 5            # limit LLM comments to top-N worst moves
    include_eval: bool = True
    include_best_move_hint: bool = True


async def export_annotated_pgn(
    session: AsyncSession, game: Game, opts: ExportOptions | None = None
) -> str:
    opts = opts or ExportOptions()

    moves = list((await session.execute(
        select(Move).where(Move.game_id == game.id).order_by(Move.ply)
    )).scalars())
    analyses = {
        a.move_id: a for a in (await session.execute(
            select(MoveAnalysis).where(MoveAnalysis.move_id.in_([m.id for m in moves]))
        )).scalars()
    }

    # Top-N worst (for LLM scoping)
    worst_set: set[int] = set()
    if opts.include_llm and opts.llm_only_worst > 0:
        scored = [
            (m.id, analyses[m.id].cp_loss or 0)
            for m in moves if m.id in analyses
            and analyses[m.id].quality in (MoveQuality.BLUNDER, MoveQuality.MISTAKE)
        ]
        scored.sort(key=lambda t: -t[1])
        worst_set = {mid for mid, _ in scored[: opts.llm_only_worst]}

    pgn_game = chess.pgn.Game()

    # Headers
    pgn_game.headers["Event"] = "Chess.com" if game.source == "chess.com" else (game.source or "Local")
    if game.url:
        pgn_game.headers["Site"] = game.url
    # We don't always have a date; use played_at if present
    if game.played_at:
        pgn_game.headers["UTCDate"] = game.played_at.strftime("%Y.%m.%d")
        pgn_game.headers["UTCTime"] = game.played_at.strftime("%H:%M:%S")
        pgn_game.headers["Date"] = pgn_game.headers["UTCDate"]
    # Player names
    pgn_game.headers["White"] = (
        await _player_name(session, game.white_player_id)
    )
    pgn_game.headers["Black"] = (
        await _player_name(session, game.black_player_id)
    )
    if game.white_rating:
        pgn_game.headers["WhiteElo"] = str(game.white_rating)
    if game.black_rating:
        pgn_game.headers["BlackElo"] = str(game.black_rating)
    if game.eco:
        pgn_game.headers["ECO"] = game.eco
    if game.opening_name:
        pgn_game.headers["Opening"] = game.opening_name
    elif game.deepest_opening_id:
        op = (await session.execute(
            select(Opening).where(Opening.id == game.deepest_opening_id)
        )).scalar_one_or_none()
        if op:
            pgn_game.headers["Opening"] = op.name
    pgn_game.headers["Result"] = str(game.result.value) if hasattr(game.result, "value") else (game.result or "*")
    if game.termination:
        pgn_game.headers["Termination"] = game.termination
    if game.time_control:
        pgn_game.headers["TimeControl"] = game.time_control
    if game.time_class:
        pgn_game.headers["TimeClass"] = str(game.time_class.value) if hasattr(game.time_class, "value") else str(game.time_class)

    # Walk moves to build the tree
    board = chess.Board(game.initial_fen) if game.initial_fen else chess.Board()
    node: chess.pgn.GameNode = pgn_game
    if game.initial_fen:
        pgn_game.setup(board)

    for m in moves:
        try:
            move = chess.Move.from_uci(m.uci)
        except (ValueError, chess.InvalidMoveError):
            continue
        if move not in board.legal_moves:
            # Database inconsistency — abort the tail of the game silently
            break
        node = node.add_main_variation(move)
        board.push(move)

        analysis = analyses.get(m.id)
        comment_parts: list[str] = []

        if analysis:
            # NAG
            nag = NAG_BY_QUALITY.get(analysis.quality) if analysis.quality else None
            if nag:
                node.nags.add(nag)

            if opts.include_eval:
                ev = _eval_comment(analysis.eval_cp, analysis.eval_mate)
                if ev:
                    comment_parts.append(ev)

            if opts.include_best_move_hint and analysis.quality in (
                MoveQuality.BLUNDER, MoveQuality.MISTAKE
            ) and analysis.best_move_san and analysis.best_move_san != m.san:
                comment_parts.append(f"better was {analysis.best_move_san}")

            # LLM coach line (only for worst N if include_llm)
            if opts.include_llm and m.id in worst_set:
                llm = _cached_llm_comment(m.fen_before, m.uci, analysis.best_move_uci)
                if llm:
                    # Keep it one-line for PGN compactness
                    one_line = " ".join(llm.split())
                    if len(one_line) > 500:
                        one_line = one_line[:497] + "..."
                    comment_parts.append(f"Coach: {one_line}")

        if comment_parts:
            existing = node.comment or ""
            node.comment = (existing + " " if existing else "") + " ".join(comment_parts)

    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    return pgn_game.accept(exporter)


async def _player_name(session: AsyncSession, player_id: int | None) -> str:
    if not player_id:
        return "?"
    from app.models import Player
    p = (await session.execute(
        select(Player).where(Player.id == player_id)
    )).scalar_one_or_none()
    return p.chesscom_username if p else "?"


async def export_with_fresh_llm(
    session: AsyncSession, game: Game, max_explanations: int = 5
) -> str:
    """Like export_annotated_pgn but generates fresh LLM comments via Ollama for the
    top-N worst player moves first (so the cache is warm). Slow!"""
    from app.models import Player
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    is_white = game.white_player_id == me.id if me else None

    moves_q = (
        select(Move.ply, MoveAnalysis.cp_loss, MoveAnalysis.quality)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(Move.game_id == game.id)
    )
    if is_white is not None:
        moves_q = moves_q.where(Move.is_white == is_white)
    moves_q = moves_q.where(
        MoveAnalysis.quality.in_((MoveQuality.BLUNDER, MoveQuality.MISTAKE))
    ).order_by(MoveAnalysis.cp_loss.desc().nullslast()).limit(max_explanations)
    worst_plies = [r[0] for r in (await session.execute(moves_q)).all()]
    for ply in worst_plies:
        try:
            await explain_move(session, game, ply, use_cache=True)
        except Exception as e:
            logger.warning("Pre-warm LLM failed at ply %s: %s", ply, e)
    return await export_annotated_pgn(
        session, game, ExportOptions(include_llm=True, llm_only_worst=max_explanations)
    )

"""Turn the player's blunders/mistakes/missed-tactics into puzzle exercises.

For each (Move, MoveAnalysis) where:
  - the move is MY move (the player whose is_me=True)
  - quality in (BLUNDER, MISTAKE)
  - the analysis has a known best_move_uci

we create one Exercise:
  - fen           = move.fen_before  (the position when I had to play)
  - side_to_move  = 'w' or 'b' derived from fen
  - solution_uci  = [best_move_uci, ...up to 4 follow-up PV moves]
  - kind          = ENDGAME if ply > 40 else TACTIC
  - difficulty    = heuristic based on cp_loss (1000-2200 range)
  - theme_tags    = list of inferred tags (missed_win, blunder_into_loss,
                    phase, drops_queen, drops_rook, drops_minor, etc.)

Idempotent thanks to UNIQUE(source_move_id).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Exercise, Game, Move, MoveAnalysis, Player
from app.models.analysis import MoveQuality
from app.models.exercise import ExerciseKind

logger = logging.getLogger(__name__)

PIECE_NAMES = {
    chess.PAWN: "drops_pawn",
    chess.KNIGHT: "drops_minor",
    chess.BISHOP: "drops_minor",
    chess.ROOK: "drops_rook",
    chess.QUEEN: "drops_queen",
}


@dataclass
class GenerationStats:
    inserted: int = 0
    skipped_existing: int = 0
    skipped_no_best: int = 0
    failed: int = 0


def _classify_phase(ply: int) -> str:
    if ply <= 20:
        return "opening"
    if ply <= 40:
        return "middlegame"
    return "endgame"


def _difficulty_from_cp_loss(cp_loss: int | None, quality: MoveQuality | None) -> int:
    """Map cp_loss to a 1000-2200 difficulty band.

    Big blunders are EASIER puzzles (the only-move is obvious in hindsight),
    subtle mistakes are HARDER. We invert linearly.
    """
    if cp_loss is None:
        return 1500
    if cp_loss <= 80:
        return 2000  # quite subtle
    if cp_loss <= 200:
        return 1700
    if cp_loss <= 500:
        return 1400
    if cp_loss <= 1000:
        return 1200
    return 1000  # huge blunder, easy to spot the right move


def _infer_themes(
    move: Move,
    analysis: MoveAnalysis,
) -> list[str]:
    themes: list[str] = [_classify_phase(move.ply)]
    if analysis.quality:
        themes.append(str(analysis.quality))

    # Missed win: position was already winning before
    if (
        (analysis.eval_mate_before is not None and analysis.eval_mate_before > 0)
        or (analysis.eval_cp_before is not None and analysis.eval_cp_before >= 300)
    ):
        themes.append("missed_win")
    # Blundered into losing: eval_after is from opponent POV
    if (
        (analysis.eval_mate is not None and analysis.eval_mate > 0)
        or (analysis.eval_cp is not None and analysis.eval_cp >= 300)
    ):
        themes.append("blundered_into_loss")

    # Was a piece on the captured square? Look at fen_after and infer from best move.
    if analysis.best_move_uci:
        board = chess.Board(move.fen_before)
        try:
            best = chess.Move.from_uci(analysis.best_move_uci)
            if board.is_capture(best):
                victim_sq = best.to_square
                captured = board.piece_at(victim_sq)
                if captured and captured.piece_type in PIECE_NAMES:
                    themes.append(PIECE_NAMES[captured.piece_type])
        except Exception:
            pass
    return themes


def _build_solution(
    move: Move,
    analysis: MoveAnalysis,
    max_followup_plies: int = 5,
) -> list[str] | None:
    if not analysis.best_move_uci:
        return None
    pv = list(analysis.pv or [])
    if not pv:
        return [analysis.best_move_uci]
    # Trust the PV — first element should equal best_move_uci
    return pv[:max_followup_plies]


def _build_title(move: Move, game: Game, themes: list[str]) -> str:
    bits = [f"Game #{game.id}, move {move.move_number}"]
    if "missed_win" in themes:
        bits.append("missed win")
    elif "blundered_into_loss" in themes:
        bits.append("avoid the loss")
    elif any(t.startswith("drops_") for t in themes):
        drop = next(t for t in themes if t.startswith("drops_"))
        bits.append(drop.replace("drops_", "saves "))
    return " — ".join(bits)


async def generate_for_player(
    session: AsyncSession,
    player: Player,
    min_cp_loss: int = 120,
) -> GenerationStats:
    stats = GenerationStats()

    my_is_white_case = (Move.is_white & (Game.white_player_id == player.id)) | (
        (~Move.is_white) & (Game.black_player_id == player.id)
    )

    q = (
        select(Move, MoveAnalysis, Game)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .join(Game, Game.id == Move.game_id)
        .where((Game.white_player_id == player.id) | (Game.black_player_id == player.id))
        .where(my_is_white_case)
        .where(MoveAnalysis.quality.in_((MoveQuality.BLUNDER, MoveQuality.MISTAKE)))
        .where(MoveAnalysis.cp_loss >= min_cp_loss)
    )
    rows = (await session.execute(q)).all()

    # Pre-fetch existing exercise source_move_ids for fast skip
    existing = {
        mid for (mid,) in (await session.execute(
            select(Exercise.source_move_id).where(Exercise.source_move_id.is_not(None))
        )).all()
    }

    now = datetime.now(timezone.utc)

    for move, analysis, game in rows:
        if move.id in existing:
            stats.skipped_existing += 1
            continue
        solution = _build_solution(move, analysis)
        if not solution:
            stats.skipped_no_best += 1
            continue
        try:
            board = chess.Board(move.fen_before)
            side = "w" if board.turn == chess.WHITE else "b"
            themes = _infer_themes(move, analysis)
            ex = Exercise(
                player_id=player.id,
                source_game_id=game.id,
                source_move_id=move.id,
                kind=ExerciseKind.ENDGAME if move.ply > 40 else ExerciseKind.TACTIC,
                title=_build_title(move, game, themes),
                fen=move.fen_before,
                side_to_move=side,
                solution_uci=solution,
                difficulty=_difficulty_from_cp_loss(analysis.cp_loss, analysis.quality),
                theme_tags=themes,
                sr_due_at=now,
            )
            session.add(ex)
            stats.inserted += 1
        except Exception as e:
            logger.warning("Failed to generate exercise for move %d: %s", move.id, e)
            stats.failed += 1

    await session.commit()
    logger.info(
        "Generated %d exercises for %s (skipped existing=%d, no-best=%d, failed=%d)",
        stats.inserted, player.chesscom_username,
        stats.skipped_existing, stats.skipped_no_best, stats.failed,
    )
    return stats

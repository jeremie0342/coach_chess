"""Detect moves where I left a piece hanging.

A "hanging piece" event:
  After MY move (fen_after), one of MY pieces (other than a pawn) is
  attacked by the opponent and either:
    - not defended at all, OR
    - defended only by lower-value pieces such that recapture nets gain.

This is a heuristic — we use a simple Static-Exchange-style check via
`board.is_attacked_by` and material delta from `python-chess`. It misses
some subtle tactics but catches the bulk of beginner-level blunders.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import chess
from sqlalchemy import case, or_, select

from app.models import Game, Move, MoveAnalysis, Player
from app.models.analysis import MoveQuality
from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding


PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


def _my_is_white_case(player_id: int) -> "case":
    return case(
        (Game.white_player_id == player_id, True),
        else_=False,
    )


def _is_hanging_after_move(fen_after: str, my_color: bool) -> tuple[bool, int]:
    """Return (is_hanging, piece_value). my_color = chess.WHITE / BLACK."""
    board = chess.Board(fen_after)
    opp_color = not my_color
    worst: int = 0
    hanging = False
    for square, piece in board.piece_map().items():
        if piece.color != my_color or piece.piece_type == chess.PAWN:
            continue
        attackers = board.attackers(opp_color, square)
        if not attackers:
            continue
        defenders = board.attackers(my_color, square)
        piece_val = PIECE_VALUE[piece.piece_type]

        if not defenders:
            hanging = True
            worst = max(worst, piece_val)
            continue
        # Cheapest attacker vs cheapest defender: if attacker < piece value
        # and exchange ends up net negative, treat as hanging
        cheapest_attacker = min(
            PIECE_VALUE[board.piece_at(a).piece_type] for a in attackers
        )
        cheapest_defender = min(
            PIECE_VALUE[board.piece_at(d).piece_type] for d in defenders
        )
        # If opponent captures and we recapture, exchange is (piece - attacker)
        net = piece_val - cheapest_attacker
        if net > 0 and cheapest_defender >= cheapest_attacker:
            # Still favorable for opponent to start the capture
            hanging = True
            worst = max(worst, piece_val)
    return hanging, worst


class HangingPieceDetector(Detector):
    category = "hanging_piece"
    requires_analysis = True
    MIN_OCCURRENCES = 4

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player
        my_is_white = _my_is_white_case(me.id)

        # Look at MY moves classified as mistake/blunder; check if hanging.
        q = (
            select(Move.id, Move.game_id, Move.fen_after, Move.is_white, Move.ply, MoveAnalysis.cp_loss)
            .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
            .join(Game, Game.id == Move.game_id)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Move.is_white == my_is_white)
            .where(MoveAnalysis.quality.in_((MoveQuality.BLUNDER, MoveQuality.MISTAKE)))
        )
        rows = (await s.execute(q)).all()

        hits: list[tuple[int, int, int]] = []  # (game_id, ply, piece_value)
        total_pv = 0
        for r in rows:
            my_color = chess.WHITE if r.is_white else chess.BLACK
            hanging, pv = _is_hanging_after_move(r.fen_after, my_color)
            if hanging:
                hits.append((r.game_id, r.ply, pv))
                total_pv += pv

        if len(hits) < self.MIN_OCCURRENCES:
            return

        seen: set[int] = set()
        samples: list[int] = []
        for gid, _, _ in hits:
            if gid not in seen:
                seen.add(gid)
                samples.append(gid)
                if len(samples) >= ctx.max_samples:
                    break

        yield WeaknessFinding(
            category=self.category,
            phase=None,
            occurrences=len(hits),
            severity=min(1.0, len(hits) / 30),
            sample_game_ids=samples,
            details={
                "total_material_dropped": total_pv,
                "avg_piece_value_dropped": round(total_pv / max(len(hits), 1), 2),
                "examples": [{"game_id": g, "ply": p, "piece_value": v} for g, p, v in hits[:10]],
            },
        )

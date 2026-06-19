"""Detect missed tactics.

A "missed tactic" event:
  - Position evaluation BEFORE my move (from my POV) was already winning or
    becoming winning (>= MIN_BEST_CP), OR Stockfish saw a mate in N.
  - I played a move with high cp_loss (>= MIN_CP_LOSS).
  - In other words: a clear forcing line was on the table and I didn't see it.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import case, or_, select

from app.models import Game, Move, MoveAnalysis, Player
from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding


def _my_is_white_case(player_id: int) -> "case":
    return case(
        (Game.white_player_id == player_id, True),
        else_=False,
    )


class MissedTacticDetector(Detector):
    category = "missed_tactic"
    requires_analysis = True
    MIN_BEST_CP = 300        # +3 advantage or better available
    MIN_CP_LOSS = 200        # 2 pawns thrown away
    MIN_OCCURRENCES = 4

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player
        my_is_white = _my_is_white_case(me.id)

        q = (
            select(
                Move.id, Move.game_id, Move.ply,
                MoveAnalysis.eval_cp_before, MoveAnalysis.eval_mate_before,
                MoveAnalysis.cp_loss, MoveAnalysis.best_move_san,
            )
            .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
            .join(Game, Game.id == Move.game_id)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Move.is_white == my_is_white)
        )
        rows = (await s.execute(q)).all()

        hits = []
        for r in rows:
            if r.cp_loss is None or r.cp_loss < self.MIN_CP_LOSS:
                continue
            winning_before = (
                (r.eval_mate_before is not None and r.eval_mate_before > 0)
                or (r.eval_cp_before is not None and r.eval_cp_before >= self.MIN_BEST_CP)
            )
            if not winning_before:
                continue
            hits.append({
                "game_id": r.game_id,
                "ply": r.ply,
                "cp_loss": r.cp_loss,
                "best_move": r.best_move_san,
                "eval_before_cp": r.eval_cp_before,
                "eval_before_mate": r.eval_mate_before,
            })

        if len(hits) < self.MIN_OCCURRENCES:
            return

        seen: set[int] = set()
        samples: list[int] = []
        for h in hits:
            if h["game_id"] not in seen:
                seen.add(h["game_id"])
                samples.append(h["game_id"])
                if len(samples) >= ctx.max_samples:
                    break

        yield WeaknessFinding(
            category=self.category,
            phase=None,
            occurrences=len(hits),
            severity=min(1.0, len(hits) / 25),
            sample_game_ids=samples,
            details={
                "min_best_cp": self.MIN_BEST_CP,
                "min_cp_loss": self.MIN_CP_LOSS,
                "examples": hits[:10],
            },
        )

"""Blunders per game phase.

Phase boundaries (in plies, total ply count of the game):
    opening    : 9..20    (after the book / before middlegame)
    middlegame : 21..40
    endgame    : 41+

Detector flags above a per-phase occurrence threshold and computes severity
relative to total moves played in that phase.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import case, func, or_, select

from app.models import Game, Move, MoveAnalysis, Player
from app.models.analysis import MoveQuality
from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding


def _my_is_white_case(player_id: int) -> "case":
    return case(
        (Game.white_player_id == player_id, True),
        else_=False,
    )


class _PhaseBlunderBase(Detector):
    """Shared logic: count MY blunders/mistakes within a ply range."""

    category = ""
    phase = ""
    ply_min: int = 0
    ply_max: int = 9999
    requires_analysis = True
    MIN_OCCURRENCES = 5

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player
        my_is_white = _my_is_white_case(me.id)

        # MY moves with blunder/mistake quality, within ply range
        bad_qualities = (MoveQuality.BLUNDER, MoveQuality.MISTAKE)
        my_moves_in_range = (
            select(MoveAnalysis.id, Move.game_id, MoveAnalysis.quality, Move.ply)
            .join(Move, Move.id == MoveAnalysis.move_id)
            .join(Game, Game.id == Move.game_id)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Move.is_white == my_is_white)
            .where(Move.ply >= self.ply_min, Move.ply <= self.ply_max)
            .where(MoveAnalysis.quality.in_(bad_qualities))
        )
        rows = (await s.execute(my_moves_in_range)).all()
        if len(rows) < self.MIN_OCCURRENCES:
            return

        # How many of my moves in this phase total (denominator)
        total_moves_q = (
            select(func.count(Move.id))
            .join(Game, Game.id == Move.game_id)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Move.is_white == my_is_white)
            .where(Move.ply >= self.ply_min, Move.ply <= self.ply_max)
        )
        total_moves = (await s.execute(total_moves_q)).scalar_one() or 1
        bad_share = len(rows) / total_moves

        # Sample game IDs (unique)
        seen: set[int] = set()
        samples: list[int] = []
        for _, gid, _, _ in rows:
            if gid not in seen:
                seen.add(gid)
                samples.append(gid)
                if len(samples) >= ctx.max_samples:
                    break

        # Split blunders / mistakes
        n_blunder = sum(1 for r in rows if r.quality == MoveQuality.BLUNDER)
        n_mistake = sum(1 for r in rows if r.quality == MoveQuality.MISTAKE)

        yield WeaknessFinding(
            category=self.category,
            phase=self.phase,
            occurrences=len(rows),
            severity=min(1.0, bad_share * 25),
            sample_game_ids=samples,
            details={
                "ply_range": [self.ply_min, self.ply_max],
                "blunders": n_blunder,
                "mistakes": n_mistake,
                "total_moves_in_phase": total_moves,
                "bad_share": round(bad_share, 4),
            },
        )


class OpeningBlunderDetector(_PhaseBlunderBase):
    category = "blunder_in_opening"
    phase = "opening"
    ply_min = 9
    ply_max = 20


class MiddlegameBlunderDetector(_PhaseBlunderBase):
    category = "blunder_in_middlegame"
    phase = "middlegame"
    ply_min = 21
    ply_max = 40


class EndgameBlunderDetector(_PhaseBlunderBase):
    category = "blunder_in_endgame"
    phase = "endgame"
    ply_min = 41
    ply_max = 9999

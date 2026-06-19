"""Detect weaknesses around recurring pawn-structure tags.

For each of the player's games, we sample the middlegame position
(ply 24 if it exists, else last move) and tag the pawn structure. We then
aggregate winrate per tag. Tags below a winrate threshold with enough
sample-size become a `weakness`.

Tags we surface as weakness categories:
  poor_with_iqp_white, poor_with_iqp_black
  poor_with_isolated_pawn, poor_with_doubled_pawns,
  poor_with_hanging_pawns, poor_with_passed_pawn_against,
  poor_with_open_files (lots of open files we don't exploit)
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import case, func, or_, select

from app.models import Game, Move
from app.models.game import GameResult
from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding
from app.services.pawn_structure import analyse


# Map raw tag → user-facing weakness category. The tag is relative to the
# pawn's owner; we re-orient based on whether the player is white or black.
def _category_for(tag: str, player_is_white: bool) -> str | None:
    if tag == "iqp_white":
        return "poor_with_iqp" if player_is_white else "poor_against_iqp"
    if tag == "iqp_black":
        return "poor_with_iqp" if not player_is_white else "poor_against_iqp"
    if tag in ("hanging_white", "hanging_black"):
        mine = tag.endswith("white") == player_is_white
        return "poor_with_hanging_pawns" if mine else "poor_against_hanging_pawns"
    if tag in ("doubled_white", "doubled_black"):
        mine = tag.endswith("white") == player_is_white
        return "poor_with_doubled_pawns" if mine else None
    if tag in ("passed_white", "passed_black"):
        mine = tag.endswith("white") == player_is_white
        return "poor_with_passed_pawn" if mine else "poor_against_passed_pawn"
    if tag in ("isolated_white", "isolated_black"):
        mine = tag.endswith("white") == player_is_white
        return "poor_with_isolated_pawns" if mine else None
    if tag == "multi_open_files":
        return "poor_with_open_position"
    return None


class PawnStructureDetector(Detector):
    """Surfaces categories where the player has a poor winrate."""

    category = "pawn_structure"
    requires_analysis = False
    MIN_GAMES_PER_CATEGORY = 10
    LOSS_THRESHOLD = 0.45
    MIDDLEGAME_SAMPLE_PLY = 24

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player

        # Pull all games + their middlegame sample FEN
        sample_fen_sub = (
            select(Move.fen_after)
            .where(Move.game_id == Game.id, Move.ply == self.MIDDLEGAME_SAMPLE_PLY)
            .scalar_subquery()
        )
        q = (
            select(Game.id, Game.white_player_id, Game.result, sample_fen_sub.label("fen24"))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        )
        rows = (await s.execute(q)).all()

        # Per (category, "my result")
        agg: dict[str, dict[str, int]] = {}
        samples: dict[str, list[int]] = {}
        for game_id, white_id, result, fen24 in rows:
            if not fen24:
                continue
            player_is_white = (white_id == me.id)
            if result == GameResult.DRAW:
                my_res = "draw"
            elif (player_is_white and result == GameResult.WHITE_WIN) or (
                not player_is_white and result == GameResult.BLACK_WIN
            ):
                my_res = "win"
            elif result in (GameResult.WHITE_WIN, GameResult.BLACK_WIN):
                my_res = "loss"
            else:
                continue
            try:
                structure = analyse(fen24)
            except Exception:
                continue
            for tag in structure.tags():
                cat = _category_for(tag, player_is_white)
                if cat is None:
                    continue
                bucket = agg.setdefault(cat, {"games": 0, "wins": 0, "draws": 0, "losses": 0})
                bucket["games"] += 1
                bucket[my_res + "s" if my_res != "loss" else "losses"] += 1
                samples.setdefault(cat, []).append(game_id)

        for cat, b in agg.items():
            if b["games"] < self.MIN_GAMES_PER_CATEGORY:
                continue
            wr = (b["wins"] + 0.5 * b["draws"]) / b["games"]
            if wr >= self.LOSS_THRESHOLD:
                continue
            severity = min(1.0, (self.LOSS_THRESHOLD - wr) * 4)
            yield WeaknessFinding(
                category=cat,
                phase="middlegame",
                occurrences=b["games"],
                severity=severity,
                sample_game_ids=samples.get(cat, [])[: ctx.max_samples],
                details={
                    "games": b["games"],
                    "wins": b["wins"], "draws": b["draws"], "losses": b["losses"],
                    "winrate": round(wr, 3),
                    "sampled_at_ply": self.MIDDLEGAME_SAMPLE_PLY,
                },
            )

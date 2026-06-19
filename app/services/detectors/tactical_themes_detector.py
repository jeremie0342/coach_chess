"""Aggregate tactical themes from MoveAnalysis.tags into Weakness rows.

Emits one Weakness per theme that crosses MIN_OCCURRENCES.
Category names match the tags themselves (e.g. 'missed_fork', 'allowed_fork')
so the lesson plan composer can map them directly to puzzle filters.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Iterable

from sqlalchemy import case, func, or_, select

from app.models import Game, Move, MoveAnalysis
from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding


THEMES_OF_INTEREST = (
    "missed_fork",
    "missed_pin",
    "missed_skewer",
    "missed_discovered_attack",
    "missed_back_rank_mate",
    "missed_mate_in_1",
    "missed_mate_in_2",
    "missed_mate_in_3",
    "trapped_piece",
    "allowed_fork",
)


class TacticalThemeDetector(Detector):
    """One weakness per theme. Severity scales with rate-per-game."""

    category = "tactical_theme"  # placeholder; we emit one finding per concrete theme
    requires_analysis = True
    MIN_OCCURRENCES = 3

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player
        my_is_white_case = case(
            (Game.white_player_id == me.id, True),
            else_=False,
        )

        # Pull all MY moves with tags
        q = (
            select(Move.game_id, Move.ply, MoveAnalysis.tags)
            .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
            .join(Game, Game.id == Move.game_id)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Move.is_white == my_is_white_case)
            .where(MoveAnalysis.tags.is_not(None))
        )
        rows = (await s.execute(q)).all()
        if not rows:
            return

        # Game count for normalisation
        total_games = (await s.execute(
            select(func.count(Game.id))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        )).scalar_one() or 1

        # theme -> list[(game_id, ply)]
        by_theme: dict[str, list[tuple[int, int]]] = {}
        for game_id, ply, tags in rows:
            if not tags:
                continue
            for t in tags:
                if t in THEMES_OF_INTEREST:
                    by_theme.setdefault(t, []).append((game_id, ply))

        for theme, occurrences in by_theme.items():
            if len(occurrences) < self.MIN_OCCURRENCES:
                continue
            unique_games = {g for g, _ in occurrences}
            rate_per_game = len(occurrences) / total_games
            # Severity: roughly tuned so 1 miss per game = 1.0
            severity = min(1.0, rate_per_game * 1.0)
            samples = list(unique_games)[: ctx.max_samples]
            yield WeaknessFinding(
                category=theme,
                phase=None,
                occurrences=len(occurrences),
                severity=severity,
                sample_game_ids=samples,
                details={
                    "theme": theme,
                    "games_affected": len(unique_games),
                    "rate_per_game": round(rate_per_game, 3),
                    "occurrences_by_game": [{"game_id": g, "ply": p} for g, p in occurrences[:20]],
                },
            )

"""Statistical detectors that work without Stockfish analysis.

These look at game-level data only: results, openings, time class, ply counts,
final clock readings, etc. They surface coarse but useful patterns quickly.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import case, func, or_, select

from app.models import Game, Move, Player
from app.models.game import GameResult
from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding


def _my_color_case(player_id: int) -> "case":
    return case(
        (Game.white_player_id == player_id, "white"),
        else_="black",
    )


def _my_result_case(player_id: int) -> "case":
    return case(
        (
            (Game.white_player_id == player_id) & (Game.result == GameResult.WHITE_WIN),
            "win",
        ),
        (
            (Game.black_player_id == player_id) & (Game.result == GameResult.BLACK_WIN),
            "win",
        ),
        (Game.result == GameResult.DRAW, "draw"),
        else_="loss",
    )


class LowWinrateOpeningDetector(Detector):
    """Flags ECO codes where I have at least N games and a winrate below threshold."""

    category = "low_winrate_opening"
    MIN_GAMES = 10
    LOSS_THRESHOLD = 0.45  # below this -> weakness

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player
        result = _my_result_case(me.id)

        q = (
            select(
                Game.eco,
                func.count(Game.id).label("n"),
                func.sum(case((result == "win", 1), else_=0)).label("wins"),
                func.sum(case((result == "loss", 1), else_=0)).label("losses"),
                func.sum(case((result == "draw", 1), else_=0)).label("draws"),
            )
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.eco.is_not(None))
            .group_by(Game.eco)
            .having(func.count(Game.id) >= self.MIN_GAMES)
        )
        rows = (await s.execute(q)).all()
        bad_openings = []
        worst_severity = 0.0
        sample_pool: list[int] = []
        total_occ = 0
        for row in rows:
            n = row.n
            winrate = (row.wins + 0.5 * row.draws) / n
            if winrate >= self.LOSS_THRESHOLD:
                continue
            severity = min(1.0, (self.LOSS_THRESHOLD - winrate) * 4)
            worst_severity = max(worst_severity, severity)
            total_occ += n
            bad_openings.append({
                "eco": row.eco,
                "games": n,
                "wins": row.wins, "losses": row.losses, "draws": row.draws,
                "winrate": round(winrate, 3),
                "severity": round(severity, 3),
            })
            # Pull a few sample game IDs (per opening)
            samples_q = (
                select(Game.id)
                .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
                .where(Game.eco == row.eco)
                .order_by(Game.played_at.desc())
                .limit(3)
            )
            sample_pool.extend(r[0] for r in (await s.execute(samples_q)).all())

        if not bad_openings:
            return
        bad_openings.sort(key=lambda d: -d["severity"])
        yield WeaknessFinding(
            category=self.category,
            phase="opening",
            occurrences=total_occ,
            severity=worst_severity,
            sample_game_ids=sample_pool[: ctx.max_samples],
            details={"openings": bad_openings},
        )


class WeakAgainstFirstMoveDetector(Detector):
    """As Black, low winrate vs 1.e4 or 1.d4 specifically."""

    category = "weak_against_first_move"
    MIN_GAMES = 8
    LOSS_THRESHOLD = 0.45

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player

        # Pull all games I played as Black + look up white's first move
        # (= move with ply=1)
        first_move_uci_subq = (
            select(Move.uci)
            .where(Move.game_id == Game.id, Move.ply == 1)
            .scalar_subquery()
        )
        result = _my_result_case(me.id)

        q = (
            select(
                first_move_uci_subq.label("first_uci"),
                func.count(Game.id).label("n"),
                func.sum(case((result == "win", 1), else_=0)).label("wins"),
                func.sum(case((result == "loss", 1), else_=0)).label("losses"),
                func.sum(case((result == "draw", 1), else_=0)).label("draws"),
            )
            .where(Game.black_player_id == me.id)
            .group_by("first_uci")
        )
        rows = (await s.execute(q)).all()
        bad: list[dict] = []
        worst_severity = 0.0
        total_occ = 0
        sample_pool: list[int] = []
        for row in rows:
            if not row.first_uci or row.n < self.MIN_GAMES:
                continue
            label = {"e2e4": "1.e4", "d2d4": "1.d4", "g1f3": "1.Nf3", "c2c4": "1.c4"}.get(
                row.first_uci, row.first_uci
            )
            winrate = (row.wins + 0.5 * row.draws) / row.n
            if winrate >= self.LOSS_THRESHOLD:
                continue
            severity = min(1.0, (self.LOSS_THRESHOLD - winrate) * 4)
            worst_severity = max(worst_severity, severity)
            total_occ += row.n
            bad.append({
                "first_move": label,
                "first_move_uci": row.first_uci,
                "games": row.n,
                "winrate": round(winrate, 3),
                "severity": round(severity, 3),
            })
            samples_q = (
                select(Game.id)
                .join(Move, (Move.game_id == Game.id) & (Move.ply == 1))
                .where(Game.black_player_id == me.id, Move.uci == row.first_uci)
                .order_by(Game.played_at.desc())
                .limit(3)
            )
            sample_pool.extend(r[0] for r in (await s.execute(samples_q)).all())

        if not bad:
            return
        bad.sort(key=lambda d: -d["severity"])
        yield WeaknessFinding(
            category=self.category,
            phase="opening",
            occurrences=total_occ,
            severity=worst_severity,
            sample_game_ids=sample_pool[: ctx.max_samples],
            details={"as_color": "black", "weak_first_moves": bad},
        )


class ColorImbalanceDetector(Detector):
    """Big winrate gap between White and Black."""

    category = "color_imbalance"
    GAP_THRESHOLD = 0.08  # 8 pts

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player
        result = _my_result_case(me.id)

        # Aggregate per color
        rows = (await s.execute(
            select(
                _my_color_case(me.id).label("color"),
                func.count(Game.id).label("n"),
                func.sum(case((result == "win", 1), else_=0)).label("wins"),
                func.sum(case((result == "draw", 1), else_=0)).label("draws"),
            )
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .group_by("color")
        )).all()
        by_color: dict[str, dict] = {}
        for r in rows:
            by_color[r.color] = {
                "n": r.n,
                "winrate": (r.wins + 0.5 * r.draws) / max(r.n, 1),
            }
        if "white" not in by_color or "black" not in by_color:
            return
        gap = by_color["white"]["winrate"] - by_color["black"]["winrate"]
        if abs(gap) < self.GAP_THRESHOLD:
            return
        weaker = "black" if gap > 0 else "white"
        yield WeaknessFinding(
            category=self.category,
            phase=None,
            occurrences=by_color[weaker]["n"],
            severity=min(1.0, abs(gap) * 4),
            sample_game_ids=[],
            details={
                "weaker_color": weaker,
                "white_winrate": round(by_color["white"]["winrate"], 3),
                "black_winrate": round(by_color["black"]["winrate"], 3),
                "gap": round(gap, 3),
            },
        )


class EarlyLossDetector(Detector):
    """I lose a lot of games in < EARLY_PLIES (= short, often opening disasters)."""

    category = "early_loss"
    EARLY_PLIES = 30  # ~15 full moves
    MIN_OCCURRENCES = 5

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player
        result = _my_result_case(me.id)

        rows_q = (
            select(Game.id)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(result == "loss")
            .where(Game.ply_count > 0)
            .where(Game.ply_count <= self.EARLY_PLIES)
        )
        ids = [r[0] for r in (await s.execute(rows_q)).all()]
        if len(ids) < self.MIN_OCCURRENCES:
            return

        total_losses = (await s.execute(
            select(func.count(Game.id))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(result == "loss")
        )).scalar_one() or 1

        share = len(ids) / total_losses
        yield WeaknessFinding(
            category=self.category,
            phase="opening",
            occurrences=len(ids),
            severity=min(1.0, share * 3),
            sample_game_ids=ids[: ctx.max_samples],
            details={
                "early_plies_threshold": self.EARLY_PLIES,
                "early_loss_share_of_all_losses": round(share, 3),
                "total_losses": total_losses,
            },
        )


class TimeTroubleDetector(Detector):
    """Many losses where my final move had very low clock.

    Heuristic: in a lost game where my last move's clock < 30s.
    """

    category = "time_trouble"
    CLOCK_THRESHOLD_S = 30
    MIN_OCCURRENCES = 5

    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        s = ctx.session
        me = ctx.player
        result = _my_result_case(me.id)

        # Most recent move per lost game where it's MY move
        my_is_white = case(
            (Game.white_player_id == me.id, True),
            else_=False,
        )

        q = (
            select(Game.id, func.min(Move.clock_seconds).label("min_clock"))
            .join(Move, Move.game_id == Game.id)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(result == "loss")
            .where(Move.is_white == my_is_white)
            .where(Move.clock_seconds.is_not(None))
            .group_by(Game.id)
            .having(func.min(Move.clock_seconds) < self.CLOCK_THRESHOLD_S)
        )
        rows = (await s.execute(q)).all()
        if len(rows) < self.MIN_OCCURRENCES:
            return
        ids = [r[0] for r in rows]
        yield WeaknessFinding(
            category=self.category,
            phase=None,
            occurrences=len(ids),
            severity=min(1.0, len(ids) / 50),
            sample_game_ids=ids[: ctx.max_samples],
            details={
                "clock_threshold_seconds": self.CLOCK_THRESHOLD_S,
                "total_lost_games_in_time_trouble": len(ids),
            },
        )

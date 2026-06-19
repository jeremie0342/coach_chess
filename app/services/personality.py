"""Compute the player's chess "personality" from their analyzed games and
compare to canonical GM archetypes.

Five orthogonal dimensions, all in [0, 1]:

  aggression       — how forcing are your moves on average? Captures + checks +
                     early piece activity.
  tactical_eye     — inverse of missed-tactic rate. High if you spot forks,
                     pins, mates; low if you miss them.
  positional       — solid in slow phases. Inverse of blunder rate in opening
                     and middlegame; bonus for long games (≥ 40 plies).
  endgame_skill    — quality in plies > 40. Inverse of endgame blunder rate
                     plus endgame winrate.
  time_management  — proxy for "you keep clock under control". 1.0 if you
                     rarely play moves with < 30s; 0.0 if always rushed.

We compare your vector to 7 GM archetypes via cosine similarity, return the
two closest matches and the dominant trait.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, MoveAnalysis, Player
from app.models.analysis import MoveQuality
from app.models.game import GameResult

logger = logging.getLogger(__name__)


@dataclass
class StyleVector:
    aggression: float
    tactical_eye: float
    positional: float
    endgame_skill: float
    time_management: float

    def as_dict(self) -> dict[str, float]:
        return {
            "aggression": round(self.aggression, 3),
            "tactical_eye": round(self.tactical_eye, 3),
            "positional": round(self.positional, 3),
            "endgame_skill": round(self.endgame_skill, 3),
            "time_management": round(self.time_management, 3),
        }


# GM archetypes — coarse subjective estimates of their dominant style.
GM_ARCHETYPES: dict[str, StyleVector] = {
    "Tal":       StyleVector(aggression=0.90, tactical_eye=0.90, positional=0.45, endgame_skill=0.65, time_management=0.55),
    "Karpov":    StyleVector(aggression=0.30, tactical_eye=0.75, positional=0.97, endgame_skill=0.95, time_management=0.80),
    "Carlsen":   StyleVector(aggression=0.55, tactical_eye=0.90, positional=0.85, endgame_skill=0.98, time_management=0.85),
    "Kasparov":  StyleVector(aggression=0.85, tactical_eye=0.92, positional=0.75, endgame_skill=0.80, time_management=0.65),
    "Petrosian": StyleVector(aggression=0.20, tactical_eye=0.65, positional=0.98, endgame_skill=0.92, time_management=0.85),
    "Anand":     StyleVector(aggression=0.60, tactical_eye=0.92, positional=0.78, endgame_skill=0.85, time_management=0.60),
    "Fischer":   StyleVector(aggression=0.75, tactical_eye=0.92, positional=0.88, endgame_skill=0.95, time_management=0.70),
}


@dataclass
class PersonalityReport:
    player: str
    moves_used: int
    style: StyleVector
    closest_gm: str | None
    closest_gm_similarity: float
    matches: list[tuple[str, float]]
    dominant_trait: str
    notes: str


def _cos_sim(a: StyleVector, b: StyleVector) -> float:
    av = [a.aggression, a.tactical_eye, a.positional, a.endgame_skill, a.time_management]
    bv = [b.aggression, b.tactical_eye, b.positional, b.endgame_skill, b.time_management]
    dot = sum(x * y for x, y in zip(av, bv))
    na = math.sqrt(sum(x * x for x in av))
    nb = math.sqrt(sum(x * x for x in bv))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


async def compute_personality(
    session: AsyncSession, player: Player
) -> PersonalityReport:
    my_is_white = case(
        (Game.white_player_id == player.id, True),
        else_=False,
    )

    base_q = (
        select(Move.id, Move.ply, Move.san, MoveAnalysis.quality,
               MoveAnalysis.cp_loss, MoveAnalysis.tags, Move.clock_seconds)
        .outerjoin(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .join(Game, Game.id == Move.game_id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Move.is_white == my_is_white)
    )
    rows = (await session.execute(base_q)).all()
    n_total = len(rows)
    # Only analyzed moves are valid for quality-based metrics
    analyzed = [r for r in rows if r.quality is not None]
    n_analyzed = len(analyzed)
    if n_analyzed < 50:
        return PersonalityReport(
            player=player.chesscom_username, moves_used=n_analyzed,
            style=StyleVector(0.5, 0.5, 0.5, 0.5, 0.5),
            closest_gm=None, closest_gm_similarity=0.0, matches=[],
            dominant_trait="undetermined",
            notes="Pas assez de coups analysés (besoin de ≥50). Lance plus d'analyses Stockfish.",
        )

    # Aggression uses ALL my moves (SAN check works without analysis)
    n_captures_checks = sum(1 for r in rows if r.san and ("x" in r.san or "+" in r.san or "#" in r.san))

    # All blunder-derived rates use only analyzed moves
    n_blunders_opening = sum(
        1 for r in analyzed
        if r.ply <= 20 and r.quality in (MoveQuality.BLUNDER, MoveQuality.MISTAKE)
    )
    n_blunders_middlegame = sum(
        1 for r in analyzed
        if 20 < r.ply <= 40 and r.quality in (MoveQuality.BLUNDER, MoveQuality.MISTAKE)
    )
    n_blunders_endgame = sum(
        1 for r in analyzed
        if r.ply > 40 and r.quality in (MoveQuality.BLUNDER, MoveQuality.MISTAKE)
    )
    n_opening = sum(1 for r in analyzed if r.ply <= 20)
    n_middle = sum(1 for r in analyzed if 20 < r.ply <= 40)
    n_end = sum(1 for r in analyzed if r.ply > 40)

    n_missed_tactics = sum(
        1 for r in analyzed if r.tags and any(t.startswith("missed_") for t in r.tags)
    )

    n_with_clock = sum(1 for r in rows if r.clock_seconds is not None)
    n_low_clock = sum(1 for r in rows if r.clock_seconds is not None and r.clock_seconds < 30)

    # Endgame winrate
    endgame_wins = (await session.execute(
        select(func.count(Game.id))
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Game.ply_count >= 41)
        .where(case(
            ((Game.white_player_id == player.id) & (Game.result == GameResult.WHITE_WIN), True),
            ((Game.black_player_id == player.id) & (Game.result == GameResult.BLACK_WIN), True),
            else_=False,
        ))
    )).scalar_one()
    endgame_total = (await session.execute(
        select(func.count(Game.id))
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Game.ply_count >= 41)
    )).scalar_one()

    # --- Build the 5D vector
    capture_check_rate = n_captures_checks / max(n_total, 1)
    aggression = _clip(capture_check_rate * 2.5)   # ~40% would saturate to 1.0

    missed_rate = n_missed_tactics / max(n_analyzed, 1)
    tactical_eye = _clip(1.0 - missed_rate * 8)    # 12.5% missed → 0

    blunder_rate_op = n_blunders_opening / max(n_opening, 1)
    blunder_rate_mid = n_blunders_middlegame / max(n_middle, 1)
    positional = _clip(
        1.0
        - blunder_rate_op * 3
        - blunder_rate_mid * 1.5
    )

    blunder_rate_end = n_blunders_endgame / max(n_end, 1)
    endgame_winrate = endgame_wins / max(endgame_total, 1)
    endgame_skill = _clip(0.7 * (1 - blunder_rate_end * 3) + 0.3 * endgame_winrate)

    low_clock_rate = n_low_clock / max(n_with_clock, 1)
    time_management = _clip(1.0 - low_clock_rate * 4)   # 25% rushed → 0

    style = StyleVector(
        aggression=aggression,
        tactical_eye=tactical_eye,
        positional=positional,
        endgame_skill=endgame_skill,
        time_management=time_management,
    )

    # --- Compare to GM archetypes
    sims = sorted(
        ((name, _cos_sim(style, vec)) for name, vec in GM_ARCHETYPES.items()),
        key=lambda t: -t[1],
    )
    closest, closest_sim = sims[0]

    # Dominant trait
    traits = style.as_dict()
    dominant = max(traits.items(), key=lambda kv: kv[1])[0]

    notes = _interpret(style, dominant, closest)

    return PersonalityReport(
        player=player.chesscom_username,
        moves_used=n_analyzed,
        style=style,
        closest_gm=closest,
        closest_gm_similarity=round(closest_sim, 3),
        matches=[(name, round(s, 3)) for name, s in sims],
        dominant_trait=dominant,
        notes=notes,
    )


def _interpret(style: StyleVector, dominant: str, closest_gm: str) -> str:
    parts: list[str] = []
    if style.aggression > 0.7:
        parts.append("Style forcing : tu captures et donnes échec souvent.")
    elif style.aggression < 0.3:
        parts.append("Style calme : peu de coups forcing.")
    if style.tactical_eye < 0.5:
        parts.append("Vision tactique limitée — drille fork/pin/mateIn2 en priorité.")
    elif style.tactical_eye > 0.8:
        parts.append("Bonne vision tactique sur ce que tu vois.")
    if style.positional > 0.7:
        parts.append("Solide en phases lentes : opening + middlegame propres.")
    elif style.positional < 0.4:
        parts.append("Beaucoup d'erreurs en opening/middlegame — travaille répertoire.")
    if style.endgame_skill > 0.7:
        parts.append("Finales bien maîtrisées.")
    elif style.endgame_skill < 0.4:
        parts.append("Faiblesse en finale — drill endgame puzzles.")
    if style.time_management < 0.5:
        parts.append("Time pressure fréquent — joue plus calmement les ouvertures.")
    parts.append(f"Profil le plus proche : {closest_gm}.")
    return " ".join(parts)

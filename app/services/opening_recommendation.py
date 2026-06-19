"""Recommend openings to learn, based on the user's play-style and current
empirical record.

Inputs we already compute elsewhere:
  - StyleVector (S32)
  - Per-ECO winrates from the user's games
  - Currently played openings (top_lines from the repertoire)

Strategy:
  - We maintain a small curated catalog of "popular openings at amateur
    level", each tagged with a style profile (aggression, tactical, etc.).
  - For each candidate opening, compute a fit score = cosine similarity
    between the user's StyleVector and the opening's profile.
  - Down-weight openings the user already plays well (>50% winrate).
  - Up-weight if it provides a clean answer to the user's weakest existing
    opening response.
  - Return the top-N candidates with a one-line rationale.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Player
from app.models.game import GameResult
from app.services.personality import StyleVector, compute_personality


# Curated catalog. style fields use the same 5 dims as StyleVector.
# 'role' = how this opening fits in your repertoire.
@dataclass
class CandidateOpening:
    name: str
    eco: str
    color: Literal["white", "black"]
    style: StyleVector
    role: str            # e.g. "vs 1.e4", "as White, attacking"
    short_pitch: str


CATALOG: list[CandidateOpening] = [
    # ---- White ----
    CandidateOpening(
        name="Italian Game (Giuoco Pianissimo + Italian Slow)",
        eco="C50", color="white",
        style=StyleVector(0.55, 0.85, 0.70, 0.75, 0.65),
        role="as White vs 1...e5",
        short_pitch="Classique, tactique mais solide. Bonne école générale.",
    ),
    CandidateOpening(
        name="London System",
        eco="D02", color="white",
        style=StyleVector(0.35, 0.65, 0.92, 0.85, 0.85),
        role="as White vs 1...d5/Nf6",
        short_pitch="Setup-based, peu de théorie, structure stable.",
    ),
    CandidateOpening(
        name="Ruy Lopez (Spanish)",
        eco="C60", color="white",
        style=StyleVector(0.55, 0.85, 0.92, 0.85, 0.65),
        role="as White vs 1...e5",
        short_pitch="L'ouverture la plus respectée. Beaucoup de plans positionnels.",
    ),
    CandidateOpening(
        name="King's Gambit",
        eco="C30", color="white",
        style=StyleVector(0.95, 0.90, 0.45, 0.60, 0.55),
        role="as White, attacking",
        short_pitch="Ultra-attaquant. Sacrifice un pion d'entrée pour l'initiative.",
    ),
    CandidateOpening(
        name="Queen's Gambit",
        eco="D06", color="white",
        style=StyleVector(0.55, 0.80, 0.90, 0.85, 0.70),
        role="as White vs 1...d5",
        short_pitch="Classique, équilibré. Apprends les structures Carlsbad et IQP.",
    ),
    CandidateOpening(
        name="Catalan",
        eco="E00", color="white",
        style=StyleVector(0.45, 0.80, 0.95, 0.90, 0.75),
        role="as White vs 1...d5/Nf6 (positional)",
        short_pitch="Positionnel pur. Fou fianchetto + pression sur a8-h1.",
    ),
    # ---- Black vs 1.e4 ----
    CandidateOpening(
        name="Sicilian Najdorf",
        eco="B90", color="black",
        style=StyleVector(0.90, 0.92, 0.65, 0.70, 0.55),
        role="vs 1.e4 (sharp, attacking)",
        short_pitch="Pour les attaquants. Asymétrique, tactique, beaucoup de théorie.",
    ),
    CandidateOpening(
        name="Caro-Kann Classical",
        eco="B18", color="black",
        style=StyleVector(0.40, 0.75, 0.92, 0.92, 0.80),
        role="vs 1.e4 (solid)",
        short_pitch="Structure de pions saine, peu de blunders d'ouverture.",
    ),
    CandidateOpening(
        name="French Defense",
        eco="C00", color="black",
        style=StyleVector(0.55, 0.75, 0.85, 0.75, 0.65),
        role="vs 1.e4 (closed positions)",
        short_pitch="Tu joues déjà — vise variantes Winawer (attaquant) ou Tarrasch.",
    ),
    CandidateOpening(
        name="Petroff (Russian Defense)",
        eco="C42", color="black",
        style=StyleVector(0.35, 0.85, 0.90, 0.85, 0.80),
        role="vs 1.e4 (symmetric, drawish)",
        short_pitch="Vise des positions claires, faible variance.",
    ),
    CandidateOpening(
        name="Scandinavian Defense",
        eco="B01", color="black",
        style=StyleVector(0.65, 0.80, 0.60, 0.70, 0.55),
        role="vs 1.e4 (sortir de la théorie)",
        short_pitch="Sors ton adversaire du livre tôt, plans simples.",
    ),
    # ---- Black vs 1.d4 ----
    CandidateOpening(
        name="King's Indian Defense",
        eco="E60", color="black",
        style=StyleVector(0.90, 0.85, 0.65, 0.70, 0.55),
        role="vs 1.d4 (attacking)",
        short_pitch="Attaque sur le roque. Sacrifices typiques en cas d'aile-fermée.",
    ),
    CandidateOpening(
        name="Slav Defense",
        eco="D10", color="black",
        style=StyleVector(0.40, 0.70, 0.92, 0.92, 0.80),
        role="vs 1.d4 (solid)",
        short_pitch="Solide, structures naturelles, peu de théorie agressive.",
    ),
    CandidateOpening(
        name="Nimzo-Indian",
        eco="E20", color="black",
        style=StyleVector(0.55, 0.85, 0.95, 0.85, 0.75),
        role="vs 1.d4 (universally respected)",
        short_pitch="Pin du Cc3 + structures dynamiques. Très étudié.",
    ),
    CandidateOpening(
        name="Modern Benoni",
        eco="A60", color="black",
        style=StyleVector(0.85, 0.90, 0.65, 0.65, 0.55),
        role="vs 1.d4 (sharp)",
        short_pitch="Asymétrique, ligne aiguë, plans clairs sur l'aile reine.",
    ),
]


@dataclass
class Recommendation:
    name: str
    eco: str
    color: str
    role: str
    fit_score: float
    short_pitch: str
    rationale: str


def _cosine(a: StyleVector, b: StyleVector) -> float:
    av = [a.aggression, a.tactical_eye, a.positional, a.endgame_skill, a.time_management]
    bv = [b.aggression, b.tactical_eye, b.positional, b.endgame_skill, b.time_management]
    dot = sum(x * y for x, y in zip(av, bv))
    na = math.sqrt(sum(x * x for x in av))
    nb = math.sqrt(sum(x * x for x in bv))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _per_eco_winrate(session: AsyncSession, player: Player) -> dict[str, float]:
    result = case(
        ((Game.white_player_id == player.id) & (Game.result == GameResult.WHITE_WIN), 1.0),
        ((Game.black_player_id == player.id) & (Game.result == GameResult.BLACK_WIN), 1.0),
        (Game.result == GameResult.DRAW, 0.5),
        else_=0.0,
    )
    rows = (await session.execute(
        select(
            Game.eco,
            func.count(Game.id).label("n"),
            func.avg(result).label("score"),
        )
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Game.eco.is_not(None))
        .group_by(Game.eco)
        .having(func.count(Game.id) >= 5)
    )).all()
    return {r.eco: float(r.score) for r in rows}


async def recommend(
    session: AsyncSession, player: Player, top_n: int = 4,
) -> list[Recommendation]:
    personality = await compute_personality(session, player)
    style = personality.style
    eco_winrate = await _per_eco_winrate(session, player)

    scored: list[Recommendation] = []
    for cand in CATALOG:
        fit = _cosine(style, cand.style)
        adjustment = 0.0
        rationale_bits = []

        # If user already plays this ECO well, deprioritize
        existing_wr = eco_winrate.get(cand.eco)
        if existing_wr is not None:
            if existing_wr >= 0.55:
                adjustment -= 0.15
                rationale_bits.append(f"déjà à {existing_wr:.0%} dans tes parties (peu de marge)")
            elif existing_wr < 0.40:
                adjustment += 0.10
                rationale_bits.append(f"actuellement {existing_wr:.0%} — beaucoup à gagner")

        # Style alignment narrative
        if fit > 0.97:
            rationale_bits.append("style très proche du tien")
        elif fit > 0.92:
            rationale_bits.append("bonne adéquation au style")
        elif fit < 0.85:
            rationale_bits.append("style différent — challenge mais formateur")

        score = fit + adjustment
        scored.append(Recommendation(
            name=cand.name, eco=cand.eco, color=cand.color,
            role=cand.role, fit_score=round(score, 3),
            short_pitch=cand.short_pitch,
            rationale=" · ".join(rationale_bits) if rationale_bits else "",
        ))

    scored.sort(key=lambda r: -r.fit_score)
    return scored[:top_n]

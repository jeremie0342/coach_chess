"""24-month training roadmap to climb from 450 to 2000 ELO.

The roadmap is split into four phases driven by the user's current Rapid
rating (self-adapting: progress fast -> next phase sooner).

  Phase A (< 900)  : foundations - heavy tactics, slow games, basic endgames
  Phase B (900-1299): main repertoire lines (Italian + Najdorf + KID), volume
  Phase C (1300-1699): anti-systems (Anti-Alapin/Moscou/London/Trompo) + calc
  Phase D (1700-2099): secondary variants (Smith-Morra, Evans, Najdorf branches)
  Phase E (>= 2100) : maintenance + targeted gap-filling

`build_phase_items` returns a list of (kind, title, count, minutes, rationale,
filters) tuples that the regular lesson_plan composer can persist.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.daily_plan import DailyItemKind


PHASE_THRESHOLDS = [
    (900, "A"),
    (1300, "B"),
    (1700, "C"),
    (2100, "D"),
]


def determine_phase(rating: int | None) -> str:
    """Return phase letter from a Rapid rating. None -> assume newcomer (A)."""
    if rating is None:
        return "A"
    for threshold, label in PHASE_THRESHOLDS:
        if rating < threshold:
            return label
    return "E"


@dataclass
class PhaseSlot:
    kind: DailyItemKind
    title: str
    minutes: int
    target_count: int
    rationale: str
    filters: dict | None = None


PHASE_TEMPLATES: dict[str, list[PhaseSlot]] = {
    "A": [
        PhaseSlot(
            kind=DailyItemKind.PUZZLE_FOCUSED,
            title="25 puzzles tactiques cibles",
            minutes=25, target_count=25,
            rationale="Phase A: fixer fork/hanging/missed_tactic. Vise tes 2 plus grosses faiblesses.",
            filters={"min_rating": 800, "max_rating": 1400},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="5 parties 15+10 sur Chess.com",
            minutes=125, target_count=5,
            rationale="Phase A: stop le blitz. 15+10 force le calcul a chaque coup. 5 parties par jour pour ancrer le rythme.",
            filters={"time_controls": ["900+10"]},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="Analyse ta partie dans le Lab",
            minutes=10, target_count=1,
            rationale="Phase A: chaque defaite doit etre regardee. Ouvre Lab d'analyse.",
            filters={"needs_lab_review": True},
        ),
        PhaseSlot(
            kind=DailyItemKind.ENDGAME_PRACTICE,
            title="Finales basiques du jour (K+P vs K)",
            minutes=20, target_count=5,
            rationale="Phase A: tu perds 180 finales gagnees. Maitrise opposition + regle du carre. 5 finales/jour.",
        ),
    ],
    "B": [
        PhaseSlot(
            kind=DailyItemKind.OPENING_STUDY,
            title="Etude ouverture du jour (Italian + Najdorf + KID)",
            minutes=15, target_count=1,
            rationale=(
                "Phase B: 1 ouverture par couleur tiree de TON repertoire. "
                "Priorite: les armes principales (Italian Game cote blanc, "
                "Najdorf vs e4, KID Mar del Plata vs d4). Lignes principales "
                "8-10 coups, on cherche le sans-faute."
            ),
        ),
        PhaseSlot(
            kind=DailyItemKind.PUZZLE_FOCUSED,
            title="15 puzzles tactiques mix",
            minutes=15, target_count=15,
            rationale="Phase B: tactique avancee, themes varies pour stabiliser ta vision.",
            filters={"min_rating": 1100, "max_rating": 1700},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="1 partie 15+10 ou 30+0",
            minutes=20, target_count=1,
            rationale="Phase B: longue suffisante pour appliquer l'ouverture etudiee.",
            filters={"time_controls": ["900+10", "1800"]},
        ),
        PhaseSlot(
            kind=DailyItemKind.ENDGAME_PRACTICE,
            title="Finale du jour (K+R vs K, opposition)",
            minutes=5, target_count=2,
            rationale="Phase B: monter en finales medianes, K+R + oppositions distantes.",
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="Analyse rapide post-partie",
            minutes=5, target_count=1,
            rationale="Phase B: focus sur l'erreur n1 dans l'ouverture et le milieu.",
            filters={"needs_lab_review": True},
        ),
    ],
    "C": [
        PhaseSlot(
            kind=DailyItemKind.OPENING_STUDY,
            title="Anti-systemes (Anti-Alapin, Anti-Moscou, Anti-London)",
            minutes=15, target_count=1,
            rationale=(
                "Phase C: tu maitrises tes lignes principales — il est temps de "
                "boucher les trous du repertoire. Drill les anti-systemes : "
                "anti-Alapin (2...d5), anti-Moscou (3...Bd7), Anti-London "
                "(KID-setup) et Anti-Trompowsky. Cela couvre les 30% de parties "
                "ou tes ouvertures principales ne sortent pas."
            ),
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="Etude d'une partie classique (Capablanca puis Tal)",
            minutes=20, target_count=1,
            rationale="Phase C: 1 partie commentee par jour. Calme avec Capablanca, ensuite Tal.",
        ),
        PhaseSlot(
            kind=DailyItemKind.PUZZLE_FOCUSED,
            title="15 puzzles longs (8-12 coups)",
            minutes=15, target_count=15,
            rationale="Phase C: calcul profond. Puzzle rush survival mode, pas race.",
            filters={"min_rating": 1500, "max_rating": 2000},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="1 partie 30+0 (ou 15+10 max)",
            minutes=20, target_count=1,
            rationale="Phase C: discipline sur le temps, force le plan avant chaque coup.",
            filters={"time_controls": ["1800", "900+10"]},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="Analyse profonde avec coach LLM",
            minutes=5, target_count=1,
            rationale="Phase C: ouvre /coach/games/X/review apres ta partie.",
            filters={"needs_lab_review": True},
        ),
    ],
    "D": [
        PhaseSlot(
            kind=DailyItemKind.OPENING_STUDY,
            title="Repertoire approfondi (Smith-Morra, Evans, Najdorf branches)",
            minutes=15, target_count=1,
            rationale=(
                "Phase D: tu connais TOUT ton repertoire. Maintenant on creuse "
                "les variantes secondaires : Smith-Morra (anti-Sicilien agressif), "
                "Evans Gambit (anti-italien), branches Najdorf (Fischer-Sozin, "
                "Adams, Bg5). Lignes jusqu'au 12e coup avec memorisation des plans."
            ),
        ),
        PhaseSlot(
            kind=DailyItemKind.PUZZLE_FOCUSED,
            title="10 puzzles ciblant tes faiblesses restantes",
            minutes=10, target_count=10,
            rationale="Phase D: laisse le backend prioriser via /coach/me/today (categories sev > 0.4).",
            filters={"min_rating": 1700, "max_rating": 2200},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="1 partie 30+0 ou 60+30",
            minutes=30, target_count=1,
            rationale="Phase D: parties longues. La 60+30 = tournoi-style 1-2 fois/semaine.",
            filters={"time_controls": ["1800", "3600+30"]},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="Analyse approfondie + pattern recurrent",
            minutes=5, target_count=1,
            rationale="Phase D: note les patterns recurrents dans un cahier. Pas que techniques: emotions, gestion du temps.",
            filters={"needs_lab_review": True},
        ),
    ],
    "E": [
        PhaseSlot(
            kind=DailyItemKind.PUZZLE_FOCUSED,
            title="20 puzzles maintenance",
            minutes=15, target_count=20,
            rationale="Phase E (>=2100): maintien tactique, themes varies.",
            filters={"min_rating": 1900, "max_rating": 2400},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="1 partie classique 60+30",
            minutes=40, target_count=1,
            rationale="Phase E: parties tournoi, analyse profonde apres.",
            filters={"time_controls": ["3600+30"]},
        ),
        PhaseSlot(
            kind=DailyItemKind.COACH_NOTE,
            title="Revue mensuelle des faiblesses residuelles",
            minutes=5, target_count=1,
            rationale="Phase E: gap-filling cible. Regarde la Constellation 1x par semaine.",
        ),
    ],
}


def build_phase_items(phase: str, target_minutes: int = 60) -> list[PhaseSlot]:
    """Return phase template.

    Target counts are authoritative (per-item daily quota set by the coach plan),
    so we no longer rescale them based on target_minutes. Time hints stay as-is.
    """
    return list(PHASE_TEMPLATES.get(phase, PHASE_TEMPLATES["A"]))


def phase_label(phase: str) -> str:
    return {
        "A": "Phase A (fondations tactiques, < 900)",
        "B": "Phase B (lignes principales: Italian/Najdorf/KID, 900-1299)",
        "C": "Phase C (anti-systemes + calcul profond, 1300-1699)",
        "D": "Phase D (repertoire complet + variantes secondaires, 1700-2099)",
        "E": "Phase E (maintenance, >= 2100)",
    }.get(phase, "Phase ?")

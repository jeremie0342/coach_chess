"""Compose the daily lesson plan for the user.

Strategy (deterministic core; LLM only writes the wrapper message):

  1. Take the top N weaknesses (sorted by severity).
  2. Map each weakness category -> recommended drill items (kind, filters,
     target_count, estimated_minutes, rationale).
  3. Always seed a repertoire_drill block if SR cards are due (memory hygiene).
  4. Trim to fit the user's time budget. Highest-severity weakness gets the
     biggest slice; smaller ones get token blocks.
  5. Persist as (DailyPlan, [DailyPlanItem...]).

Idempotent per (player_id, plan_date). Re-querying the same day returns
the same plan unless `force=True`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DailyPlan,
    DailyPlanItem,
    Exercise,
    Player,
    RepertoireNode,
    Weakness,
)
from app.models.daily_plan import DailyItemKind


# How much time a single rep of each item kind costs (heuristic).
MINUTES_PER_UNIT = {
    DailyItemKind.REPERTOIRE_DRILL: 0.3,
    DailyItemKind.PUZZLE_FOCUSED: 1.0,
    DailyItemKind.BLUNDER_REVIEW: 1.5,
    DailyItemKind.ENDGAME_PRACTICE: 1.5,
    DailyItemKind.OPENING_STUDY: 2.0,
    DailyItemKind.COACH_NOTE: 0.0,
}


# Weakness category → puzzle theme(s) we should drill. None means no clean
# theme exists; fall back to a generic kind.
WEAKNESS_TO_THEME: dict[str, list[str]] = {
    # Coarse categories (kept as fallbacks if no fine-grained data yet)
    "missed_tactic":         ["fork", "pin", "skewer", "discoveredAttack"],
    "hanging_piece":         ["hangingPiece", "trapped"],
    "blunder_in_opening":    [],
    "blunder_in_middlegame": ["middlegame", "advantage"],
    "blunder_in_endgame":    ["endgame", "rookEndgame", "pawnEndgame"],
    "early_loss":            [],
    "low_winrate_opening":   [],
    "weak_against_first_move": [],
    "time_trouble":          [],
    "color_imbalance":       [],
    # Fine-grained tactical themes from TacticalThemeDetector
    "missed_fork":              ["fork"],
    "missed_pin":               ["pin"],
    "missed_skewer":            ["skewer"],
    "missed_discovered_attack": ["discoveredAttack"],
    "missed_back_rank_mate":    ["backRankMate"],
    "missed_mate_in_1":         ["mateIn1"],
    "missed_mate_in_2":         ["mateIn2"],
    "missed_mate_in_3":         ["mateIn3"],
    "trapped_piece":            ["trapped", "hangingPiece"],
    "allowed_fork":             ["fork"],
}


@dataclass
class _Candidate:
    kind: DailyItemKind
    title: str
    target_count: int
    filters: dict
    rationale: str
    priority: float  # severity-derived


def _round_robin_theme(themes: list[str], used_at_index: int) -> str | None:
    if not themes:
        return None
    return themes[used_at_index % len(themes)]


def _make_puzzle_item(
    severity: float,
    rationale: str,
    theme: str | None,
    rating: int | None,
    count: int,
) -> _Candidate:
    filters: dict = {"source_kind": "lichess"}
    if rating is not None:
        filters["rating"] = rating
        filters["rating_window"] = 200
    if theme:
        filters["theme"] = theme
    title = f"{count} puzzles {theme}" if theme else f"{count} puzzles ciblés"
    return _Candidate(
        kind=DailyItemKind.PUZZLE_FOCUSED,
        title=title,
        target_count=count,
        filters=filters,
        rationale=rationale,
        priority=severity,
    )


async def _due_repertoire_count(session: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    return (await session.execute(
        select(func.count(RepertoireNode.id))
        .where(RepertoireNode.is_my_move.is_(True))
        .where(RepertoireNode.sr_due_at.is_not(None), RepertoireNode.sr_due_at <= now)
    )).scalar_one()


async def _due_blunder_exercise_count(session: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    return (await session.execute(
        select(func.count(Exercise.id))
        .where(Exercise.source_kind == "blunder")
        .where(Exercise.sr_due_at.is_not(None), Exercise.sr_due_at <= now)
    )).scalar_one()


async def _current_rapid_rating(session: AsyncSession, player_id: int) -> int | None:
    from sqlalchemy import case
    from app.models import Game
    my_rating = case(
        (Game.white_player_id == player_id, Game.white_rating),
        else_=Game.black_rating,
    )
    return (await session.execute(
        select(my_rating)
        .where(((Game.white_player_id == player_id) | (Game.black_player_id == player_id)))
        .where(Game.time_class == "rapid")
        .where(my_rating.is_not(None))
        .order_by(Game.played_at.desc())
        .limit(1)
    )).scalar()


async def _build_candidates(
    session: AsyncSession, player: Player
) -> tuple[list[_Candidate], list[Weakness], int | None]:
    weaknesses = list((await session.execute(
        select(Weakness)
        .where(Weakness.player_id == player.id)
        .order_by(Weakness.severity.desc())
        .limit(10)
    )).scalars())

    rating = await _current_rapid_rating(session, player.id)
    candidates: list[_Candidate] = []

    # Repertoire drill: always a candidate if cards are due.
    rep_due = await _due_repertoire_count(session)
    if rep_due > 0:
        n = min(20, rep_due)
        candidates.append(_Candidate(
            kind=DailyItemKind.REPERTOIRE_DRILL,
            title=f"Revoir {n} positions de ton répertoire",
            target_count=n,
            filters={},
            rationale=f"{rep_due} cartes dues aujourd'hui (mémoire d'ouverture)",
            priority=0.85,  # always-on hygiene; trumps low-severity puzzle blocks
        ))

    # Blunder review: always a baseline if blunders exist
    bl_due = await _due_blunder_exercise_count(session)
    if bl_due > 0:
        n = min(10, bl_due)
        candidates.append(_Candidate(
            kind=DailyItemKind.BLUNDER_REVIEW,
            title=f"Revoir {n} de tes propres erreurs",
            target_count=n,
            filters={"source_kind": "blunder"},
            rationale="Revoir tes patterns d'erreur passés",
            priority=0.55,
        ))

    # Weakness-driven items
    theme_round = 0
    for w in weaknesses:
        themes = WEAKNESS_TO_THEME.get(w.category, [])

        if themes:
            theme = _round_robin_theme(themes, theme_round)
            theme_round += 1
            # Number of puzzles ~ proportional to severity
            count = max(5, min(20, int(round(15 * w.severity))))
            rationale = _explain_weakness(w)
            candidates.append(_make_puzzle_item(
                severity=w.severity,
                rationale=rationale,
                theme=theme,
                rating=rating,
                count=count,
            ))
        elif w.category in ("low_winrate_opening", "weak_against_first_move", "early_loss"):
            # Bump the repertoire item rationale if present (no extra item)
            for cand in candidates:
                if cand.kind == DailyItemKind.REPERTOIRE_DRILL:
                    cand.rationale = (
                        cand.rationale + f" · cible {w.category} (sev {w.severity:.2f})"
                    )
                    cand.priority = max(cand.priority, 0.7 + w.severity * 0.3)
                    break
        elif w.category in ("time_trouble", "color_imbalance"):
            candidates.append(_Candidate(
                kind=DailyItemKind.COACH_NOTE,
                title=f"Note du coach: {w.category}",
                target_count=0,
                filters={"weakness_category": w.category},
                rationale=_explain_weakness(w),
                priority=w.severity * 0.5,
            ))

    return candidates, weaknesses, rating


def _explain_weakness(w: Weakness) -> str:
    base = {
        "missed_tactic":          "Tactiques ratées en cours de partie",
        "hanging_piece":          "Pièces laissées en prise",
        "blunder_in_opening":     "Blunders en ouverture",
        "blunder_in_middlegame":  "Blunders en milieu de jeu",
        "blunder_in_endgame":     "Blunders en finale",
        "early_loss":             "Tu perds tôt dans la partie",
        "low_winrate_opening":    "Une ouverture sous-performante",
        "weak_against_first_move":"Mauvais score contre certain premier coup",
        "time_trouble":           "Tu joues souvent en time-trouble",
        "color_imbalance":        "Grand écart de winrate entre Blanc et Noir",
    }.get(w.category, w.category)
    return f"{base} (sévérité {w.severity:.2f}, {w.occurrences} occurrences)"


def _fit_to_budget(
    candidates: list[_Candidate], target_minutes: int
) -> list[_Candidate]:
    """Greedy selection by priority, trim counts to fit budget."""
    candidates_sorted = sorted(candidates, key=lambda c: -c.priority)
    picked: list[_Candidate] = []
    used = 0.0
    for c in candidates_sorted:
        cost_per = MINUTES_PER_UNIT.get(c.kind, 1.0)
        if c.kind == DailyItemKind.COACH_NOTE:
            picked.append(c)
            continue
        if c.target_count == 0:
            continue
        full_cost = c.target_count * cost_per
        if used + full_cost <= target_minutes:
            picked.append(c)
            used += full_cost
        else:
            # trim
            remaining = max(0, target_minutes - used)
            new_count = int(remaining // cost_per)
            if new_count >= 3:  # not worth keeping otherwise
                c.target_count = new_count
                picked.append(c)
                used += new_count * cost_per
    return picked


def _estimate_minutes(kind: DailyItemKind, count: int) -> int:
    return max(1, int(round(MINUTES_PER_UNIT.get(kind, 1.0) * count)))


async def compose_daily_plan(
    session: AsyncSession,
    player: Player,
    plan_date: date | None = None,
    target_minutes: int = 30,
    force: bool = False,
) -> DailyPlan:
    plan_date = plan_date or datetime.now(timezone.utc).date()

    existing = (await session.execute(
        select(DailyPlan).where(
            and_(DailyPlan.player_id == player.id, DailyPlan.plan_date == plan_date)
        )
    )).scalar_one_or_none()
    if existing and not force:
        return existing
    if existing and force:
        await session.delete(existing)
        await session.flush()

    candidates, weaknesses, _rating = await _build_candidates(session, player)
    chosen = _fit_to_budget(candidates, target_minutes)

    focus = weaknesses[0].category if weaknesses else None
    plan = DailyPlan(
        player_id=player.id,
        plan_date=plan_date,
        target_minutes=target_minutes,
        weakness_focus=focus,
    )
    session.add(plan)
    await session.flush()

    for idx, c in enumerate(chosen):
        session.add(DailyPlanItem(
            plan_id=plan.id,
            order_index=idx,
            kind=c.kind,
            title=c.title,
            target_count=c.target_count,
            estimated_minutes=_estimate_minutes(c.kind, c.target_count),
            filters=c.filters,
            rationale=c.rationale,
        ))
    await session.commit()
    return plan

"""Build the player's weekly report.

Pulls structured numbers (deltas from snapshots, games played, puzzles
solved) + invokes Ollama for a 3-4 paragraph narrative debrief. Persists
in `weekly_reports`. Idempotent per (player_id, week_start).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DailyPlan,
    Game,
    MetricSnapshot,
    Player,
    Weakness,
    WeeklyReport,
)
from app.models.analysis import MoveQuality
from app.models.game import GameResult
from app.models.move import Move
from app.models.analysis import MoveAnalysis
from app.services.llm.ollama import ChatMessage, OllamaClient

logger = logging.getLogger(__name__)


COACH_SYSTEM = """Tu es un coach d'échecs francophone, motivant et concret. Tu écris le résumé hebdomadaire d'entraînement de ton joueur (~450 ELO, vise 2000).

Le résumé doit :
- Faire 3 paragraphes maximum, ton chaleureux mais sans flagornerie.
- Para 1 : ce qui a été fait cette semaine (chiffres clés).
- Para 2 : ce qui a progressé (Δ sévérités, Elo, etc.) et ce qui n'a pas bougé.
- Para 3 : LA priorité concrète pour la semaine suivante. Sois spécifique : un thème de puzzle, un type de finale, une ouverture précise.

Pas de listes à puces. Pas de markdown. Pas de cliché type 'continue comme ça'."""


@dataclass
class WeeklyData:
    week_start: date
    week_end: date
    games_played: int
    elo_first: int | None
    elo_last: int | None
    puzzles_solved: int
    rep_cards_reviewed: int
    plans_completed: int
    blunders: int
    weakness_deltas: dict[str, float]   # category -> delta severity (negative = improved)
    current_top_weaknesses: list[dict]   # latest top 5 weaknesses


async def _gather_data(session: AsyncSession, player: Player) -> WeeklyData:
    now = datetime.now(timezone.utc)
    week_end = now.date()
    week_start = week_end - timedelta(days=7)

    # Find the earliest snapshot before/in this week (anchor) and the latest
    base_q = (
        select(MetricSnapshot)
        .where(MetricSnapshot.player_id == player.id)
        .order_by(MetricSnapshot.taken_at.asc())
    )
    early = (await session.execute(
        base_q.where(MetricSnapshot.taken_at >= now - timedelta(days=14)).limit(1)
    )).scalar_one_or_none()
    latest = (await session.execute(
        select(MetricSnapshot)
        .where(MetricSnapshot.player_id == player.id)
        .order_by(MetricSnapshot.taken_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    elo_first = early.rating_rapid if early else None
    elo_last = latest.rating_rapid if latest else None

    # Games this week
    base_games = or_(
        Game.white_player_id == player.id, Game.black_player_id == player.id
    )
    games_played = (await session.execute(
        select(func.count(Game.id))
        .where(base_games)
        .where(Game.played_at >= now - timedelta(days=7))
    )).scalar_one()

    # Blunders/mistakes by me this week
    my_is_white = case((Game.white_player_id == player.id, True), else_=False)
    blunders = (await session.execute(
        select(func.count(Move.id))
        .join(Game, Game.id == Move.game_id)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(base_games)
        .where(Game.played_at >= now - timedelta(days=7))
        .where(Move.is_white == my_is_white)
        .where(MoveAnalysis.quality.in_((MoveQuality.BLUNDER, MoveQuality.MISTAKE)))
    )).scalar_one()

    # Use latest snapshot's headline stats where available
    puzzles_7d = latest.exercises_solved_7d if latest else 0
    rep_7d = latest.rep_cards_reviewed_7d if latest else 0

    plans_completed = (await session.execute(
        select(func.count(DailyPlan.id))
        .where(DailyPlan.player_id == player.id)
        .where(DailyPlan.completed_at >= now - timedelta(days=7))
    )).scalar_one()

    # Weakness deltas (early vs latest)
    deltas: dict[str, float] = {}
    if early and latest:
        early_sev = early.weakness_severities or {}
        late_sev = latest.weakness_severities or {}
        cats = set(early_sev) | set(late_sev)
        for c in cats:
            e = float(early_sev.get(c, 0))
            l = float(late_sev.get(c, 0))
            if abs(l - e) >= 0.02:
                deltas[c] = round(l - e, 3)

    # Current top weaknesses
    top_w = list((await session.execute(
        select(Weakness)
        .where(Weakness.player_id == player.id)
        .order_by(Weakness.severity.desc())
        .limit(5)
    )).scalars())
    current_top = [
        {"category": w.category, "phase": w.phase, "severity": round(w.severity, 3)}
        for w in top_w
    ]

    return WeeklyData(
        week_start=week_start,
        week_end=week_end,
        games_played=games_played,
        elo_first=elo_first,
        elo_last=elo_last,
        puzzles_solved=int(puzzles_7d),
        rep_cards_reviewed=int(rep_7d),
        plans_completed=int(plans_completed),
        blunders=int(blunders),
        weakness_deltas=deltas,
        current_top_weaknesses=current_top,
    )


def _format_prompt(data: WeeklyData) -> str:
    elo_delta = "?"
    if data.elo_first is not None and data.elo_last is not None:
        elo_delta = f"{data.elo_last - data.elo_first:+d}"
    lines = [
        f"Période : {data.week_start} → {data.week_end}",
        f"Parties jouées : {data.games_played}",
        f"Elo rapid : {data.elo_first or '?'} → {data.elo_last or '?'}  (Δ {elo_delta})",
        f"Puzzles résolus (7j) : {data.puzzles_solved}",
        f"Cartes répertoire revues (7j) : {data.rep_cards_reviewed}",
        f"Plans complétés (7j) : {data.plans_completed}",
        f"Blunders dans tes parties (7j) : {data.blunders}",
        "",
        "Variations de sévérité (négatif = tu progresses) :",
    ]
    if not data.weakness_deltas:
        lines.append("  (pas de variation notable)")
    else:
        for cat, d in sorted(data.weakness_deltas.items(), key=lambda kv: kv[1]):
            arrow = "↓" if d < 0 else "↑"
            lines.append(f"  {cat}: {arrow} {d:+.3f}")
    lines.append("")
    lines.append("Top faiblesses actuelles :")
    for w in data.current_top_weaknesses:
        phase = f" [{w['phase']}]" if w.get("phase") else ""
        lines.append(f"  - {w['category']}{phase} (sev {w['severity']})")
    lines.append("")
    lines.append("Rédige le résumé hebdomadaire.")
    return "\n".join(lines)


async def generate_weekly_report(
    session: AsyncSession, player: Player, *, force: bool = False
) -> WeeklyReport:
    data = await _gather_data(session, player)

    existing = (await session.execute(
        select(WeeklyReport).where(
            and_(
                WeeklyReport.player_id == player.id,
                WeeklyReport.week_start == data.week_start,
            )
        )
    )).scalar_one_or_none()
    if existing and not force:
        return existing
    if existing and force:
        await session.delete(existing)
        await session.flush()

    narrative: str | None = None
    focus: str | None = None
    try:
        async with OllamaClient() as client:
            narrative = await client.chat(
                [
                    ChatMessage(role="system", content=COACH_SYSTEM),
                    ChatMessage(role="user", content=_format_prompt(data)),
                ],
                temperature=0.5,
                num_predict=400,
            )
        if data.current_top_weaknesses:
            focus = data.current_top_weaknesses[0]["category"]
    except Exception as e:
        logger.warning("Weekly LLM narrative failed: %s", e)

    elo_delta = 0
    if data.elo_first is not None and data.elo_last is not None:
        elo_delta = data.elo_last - data.elo_first

    report = WeeklyReport(
        player_id=player.id,
        week_start=data.week_start,
        week_end=data.week_end,
        generated_at=datetime.now(timezone.utc),
        games_played=data.games_played,
        elo_delta=elo_delta,
        puzzles_solved=data.puzzles_solved,
        rep_cards_reviewed=data.rep_cards_reviewed,
        plans_completed=data.plans_completed,
        blunders_this_week=data.blunders,
        weakness_deltas=data.weakness_deltas,
        top_focus_for_next_week=focus,
        narrative=narrative,
    )
    session.add(report)
    await session.commit()

    # Best-effort notification to Discord/Slack if configured
    try:
        from app.services.webhooks import WebhookField, WebhookMessage, notify
        await notify(WebhookMessage(
            title=f"Coach hebdo — semaine {data.week_start.isoformat()}",
            description=(narrative or "")[:1500],
            fields=[
                WebhookField("Parties", str(data.games_played)),
                WebhookField("Elo Δ", f"{elo_delta:+d}"),
                WebhookField("Blunders", str(data.blunders)),
                WebhookField("Focus suivant", focus or "-"),
            ],
        ))
    except Exception as e:
        logger.warning("Weekly notify failed: %s", e)
    return report

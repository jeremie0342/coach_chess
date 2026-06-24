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
    # Rich breakdown
    details: dict = None  # populated by _gather_details


def _phase_of(ply: int) -> str:
    if ply <= 20:
        return "opening"
    if ply <= 60:
        return "middlegame"
    return "endgame"


def _result_for(player_id: int, g: Game) -> str:
    if g.result == GameResult.DRAW:
        return "draw"
    won_white = g.white_player_id == player_id and g.result == GameResult.WHITE_WIN
    won_black = g.black_player_id == player_id and g.result == GameResult.BLACK_WIN
    return "win" if (won_white or won_black) else "loss"


_RESULT_BUCKET = {"win": "wins", "loss": "losses", "draw": "draws"}


async def _gather_details(
    session: AsyncSession, player: Player, since: datetime, prev_since: datetime,
) -> dict:
    """Compute the rich-report stats. All bound to player's games this week
    (and the previous week for comparison)."""
    base_filter = or_(
        Game.white_player_id == player.id, Game.black_player_id == player.id
    )
    this_week = list((await session.execute(
        select(Game)
        .where(base_filter)
        .where(Game.played_at >= since)
        .order_by(Game.played_at.desc())
    )).scalars())
    prev_week = list((await session.execute(
        select(Game)
        .where(base_filter)
        .where(Game.played_at >= prev_since)
        .where(Game.played_at < since)
    )).scalars())

    # --- W/L/D + by color + by time_class -----------------------------------
    bilan = {"wins": 0, "losses": 0, "draws": 0}
    by_color: dict[str, dict] = {"white": {"wins": 0, "losses": 0, "draws": 0},
                                 "black": {"wins": 0, "losses": 0, "draws": 0}}
    by_tc: dict[str, dict] = {}
    out_of_book_plies: list[int] = []

    for g in this_week:
        r = _result_for(player.id, g)
        bucket = _RESULT_BUCKET[r]
        bilan[bucket] += 1
        color = "white" if g.white_player_id == player.id else "black"
        by_color[color][bucket] += 1
        tc = g.time_class or "unknown"
        d = by_tc.setdefault(tc, {"wins": 0, "losses": 0, "draws": 0})
        d[bucket] += 1
        if g.my_out_of_book_ply is not None:
            out_of_book_plies.append(g.my_out_of_book_ply)

    avg_out_of_book = (
        round(sum(out_of_book_plies) / len(out_of_book_plies), 1)
        if out_of_book_plies else None
    )

    # --- Phase quality breakdown -------------------------------------------
    # Count user's blunders/mistakes/inaccuracies per phase for this week
    this_week_ids = [g.id for g in this_week]
    phase_quality: dict[str, dict] = {
        "opening": {"moves": 0, "blunders": 0, "mistakes": 0, "inaccuracies": 0},
        "middlegame": {"moves": 0, "blunders": 0, "mistakes": 0, "inaccuracies": 0},
        "endgame": {"moves": 0, "blunders": 0, "mistakes": 0, "inaccuracies": 0},
    }
    if this_week_ids:
        my_is_white_case = case(
            (Game.white_player_id == player.id, True), else_=False,
        )
        rows = (await session.execute(
            select(Move.ply, Move.is_white, Game.white_player_id, MoveAnalysis.quality)
            .join(Game, Game.id == Move.game_id)
            .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
            .where(Move.game_id.in_(this_week_ids))
        )).all()
        for ply, is_white, wp, quality in rows:
            if (wp == player.id) != bool(is_white):
                continue
            ph = phase_quality[_phase_of(ply)]
            ph["moves"] += 1
            if quality == MoveQuality.BLUNDER:
                ph["blunders"] += 1
            elif quality == MoveQuality.MISTAKE:
                ph["mistakes"] += 1
            elif quality == MoveQuality.INACCURACY:
                ph["inaccuracies"] += 1

    # --- Top 5 worst moves of the week -------------------------------------
    top_blunders: list[dict] = []
    if this_week_ids:
        rows = (await session.execute(
            select(Move, MoveAnalysis, Game)
            .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
            .join(Game, Game.id == Move.game_id)
            .where(Move.game_id.in_(this_week_ids))
            .where(
                or_(
                    and_(Move.is_white.is_(True), Game.white_player_id == player.id),
                    and_(Move.is_white.is_(False), Game.black_player_id == player.id),
                )
            )
            .where(MoveAnalysis.quality.in_((MoveQuality.BLUNDER, MoveQuality.MISTAKE)))
            .order_by(MoveAnalysis.cp_loss.desc().nullslast())
            .limit(5)
        )).all()
        for m, a, g in rows:
            top_blunders.append({
                "game_id": g.id,
                "played_at": g.played_at.isoformat() if g.played_at else None,
                "ply": m.ply,
                "played_san": m.san,
                "best_san": a.best_move_san,
                "quality": str(a.quality) if a.quality else None,
                "cp_loss": a.cp_loss,
            })

    # --- Best win + worst loss ---------------------------------------------
    best_win = None
    worst_loss = None
    if this_week:
        wins = [g for g in this_week if _result_for(player.id, g) == "win"]
        losses = [g for g in this_week if _result_for(player.id, g) == "loss"]
        # "Best" = highest-rated opponent we beat
        def opp_rating(g: Game) -> int:
            is_me_white = g.white_player_id == player.id
            return (g.black_rating if is_me_white else g.white_rating) or 0
        if wins:
            best = max(wins, key=opp_rating)
            best_win = {
                "game_id": best.id,
                "opp_rating": opp_rating(best),
                "color": "white" if best.white_player_id == player.id else "black",
                "opening": best.opening_name,
                "time_class": str(best.time_class) if best.time_class else None,
                "played_at": best.played_at.isoformat() if best.played_at else None,
            }
        if losses:
            # "Worst" = lowest-rated opponent we lost to
            worst = min(losses, key=opp_rating)
            worst_loss = {
                "game_id": worst.id,
                "opp_rating": opp_rating(worst),
                "color": "white" if worst.white_player_id == player.id else "black",
                "opening": worst.opening_name,
                "time_class": str(worst.time_class) if worst.time_class else None,
                "played_at": worst.played_at.isoformat() if worst.played_at else None,
            }

    # --- Consistency: days played this week + streak -----------------------
    days_set = {g.played_at.date() for g in this_week if g.played_at}
    days_played = len(days_set)

    # Streak: count consecutive days ending today/yesterday with at least one game
    today = datetime.now(timezone.utc).date()
    streak = 0
    cursor = today
    all_days = {g.played_at.date() for g in this_week if g.played_at}
    # Also pull prev week to extend the streak back
    for g in prev_week:
        if g.played_at:
            all_days.add(g.played_at.date())
    while cursor in all_days:
        streak += 1
        cursor -= timedelta(days=1)
    # If today has no game but yesterday does, the streak is still alive
    if streak == 0 and (today - timedelta(days=1)) in all_days:
        cursor = today - timedelta(days=1)
        while cursor in all_days:
            streak += 1
            cursor -= timedelta(days=1)

    # --- Comparison with previous week -------------------------------------
    prev_count = len(prev_week)
    prev_wins = sum(1 for g in prev_week if _result_for(player.id, g) == "win")
    prev_blunders_q = (await session.execute(
        select(func.count(Move.id))
        .join(Game, Game.id == Move.game_id)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .where(Game.played_at >= prev_since)
        .where(Game.played_at < since)
        .where(
            or_(
                and_(Move.is_white.is_(True), Game.white_player_id == player.id),
                and_(Move.is_white.is_(False), Game.black_player_id == player.id),
            )
        )
        .where(MoveAnalysis.quality.in_((MoveQuality.BLUNDER, MoveQuality.MISTAKE)))
    )).scalar_one()

    # --- Top openings this week --------------------------------------------
    opening_stats: dict[str, dict] = {}
    for g in this_week:
        key = g.opening_name or "Unknown"
        d = opening_stats.setdefault(key, {"games": 0, "wins": 0, "losses": 0, "draws": 0, "eco": g.eco})
        d["games"] += 1
        r = _result_for(player.id, g)
        d[_RESULT_BUCKET[r]] += 1
    top_openings = sorted(
        ({"name": k, **v, "winrate": round((v["wins"] + 0.5 * v["draws"]) / max(v["games"], 1), 3)}
         for k, v in opening_stats.items()),
        key=lambda x: x["games"], reverse=True,
    )[:6]

    return {
        "bilan": bilan,
        "by_color": by_color,
        "by_time_class": by_tc,
        "phase_quality": phase_quality,
        "avg_out_of_book_ply": avg_out_of_book,
        "top_blunders": top_blunders,
        "best_win": best_win,
        "worst_loss": worst_loss,
        "days_played": days_played,
        "streak": streak,
        "top_openings": top_openings,
        "vs_prev_week": {
            "games_played_prev": prev_count,
            "wins_prev": prev_wins,
            "blunders_prev": int(prev_blunders_q),
            "games_delta": len(this_week) - prev_count,
            "wins_delta": bilan["wins"] - prev_wins,
            "blunders_delta": None,  # filled by caller (has access to current blunders)
        },
    }


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

    details = await _gather_details(
        session, player,
        since=now - timedelta(days=7),
        prev_since=now - timedelta(days=14),
    )
    # Fill the blunders delta now that we have the count
    if details.get("vs_prev_week"):
        details["vs_prev_week"]["blunders_delta"] = int(blunders) - details["vs_prev_week"]["blunders_prev"]
    # Stash a copy of the headline numbers in details for self-contained rendering
    details["headline"] = {
        "games_played": games_played,
        "elo_first": elo_first,
        "elo_last": elo_last,
        "elo_delta": (elo_last - elo_first) if (elo_first is not None and elo_last is not None) else None,
        "puzzles_solved": int(puzzles_7d),
        "rep_cards_reviewed": int(rep_7d),
        "plans_completed": int(plans_completed),
        "blunders": int(blunders),
    }
    details["current_top_weaknesses"] = current_top
    details["weakness_deltas"] = deltas

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
        details=details,
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
        details=data.details,
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

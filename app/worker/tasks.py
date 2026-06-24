"""Arq tasks: thin wrappers around our existing services.

Each task:
  - Receives `ctx` (arq runtime ctx) as first arg
  - Opens a fresh AsyncSession
  - Calls the underlying service
  - Returns a JSON-serialisable dict

Long-running tasks may report progress by writing to `ctx['job_try_progress']`
(we keep this simple — for finer progress, switch to enqueue/aggregate
sub-jobs later).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Game, Player
from app.services.analyzer import analyze_game
from app.services.exercises.generator import generate_for_player
from app.services.import_orchestrator import (
    import_full_history,
    import_month,
    import_recent_months,
)
from app.services.live_debrief import live_debrief
from app.services.openings.out_of_book import compute_out_of_book_for_all_my_games
from app.services.openings.repertoire_builder import build_repertoire
from app.services.scout.scout import scout_opponent
from app.services.stockfish import get_engine
from app.services.weakness_engine import refresh_player_weaknesses

logger = logging.getLogger(__name__)


# ---------- Stockfish-driven ----------

async def analyze_game_task(ctx: dict, game_id: int, depth: int | None = None, force: bool = False) -> dict:
    async with SessionLocal() as session:
        game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
        if not game:
            return {"error": f"game {game_id} not found"}
        engine = await get_engine()
        stats = await analyze_game(session, game, engine, depth=depth, force=force)
        return {
            "game_id": stats.game_id,
            "moves_analyzed": stats.moves_analyzed,
            "blunders": stats.blunders,
            "mistakes": stats.mistakes,
            "inaccuracies": stats.inaccuracies,
            "elapsed_s": round(stats.elapsed_s, 2),
        }


async def analyze_pending_task(
    ctx: dict,
    limit: int = 100,
    depth: int | None = None,
    since_rating: int | None = None,
) -> dict:
    """Analyze pending games. Long-running: re-enqueue self if more remain."""
    from sqlalchemy import case, or_
    async with SessionLocal() as session:
        q = select(Game).where(Game.analysis_status == "pending")
        if since_rating is not None:
            me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
            if me:
                my_rating = case(
                    (Game.white_player_id == me.id, Game.white_rating),
                    else_=Game.black_rating,
                )
                threshold_played_at = (await session.execute(
                    select(Game.played_at)
                    .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
                    .where(my_rating >= since_rating)
                    .order_by(Game.played_at.asc())
                    .limit(1)
                )).scalar()
                if threshold_played_at is not None:
                    q = q.where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
                    q = q.where(Game.played_at >= threshold_played_at)
        q = q.order_by(Game.played_at.desc()).limit(limit)
        games = list((await session.execute(q)).scalars())

        engine = await get_engine()
        total = {"games": 0, "moves": 0, "blunders": 0, "mistakes": 0, "inaccuracies": 0}
        for g in games:
            s = await analyze_game(session, g, engine, depth=depth)
            total["games"] += 1
            total["moves"] += s.moves_analyzed
            total["blunders"] += s.blunders
            total["mistakes"] += s.mistakes
            total["inaccuracies"] += s.inaccuracies
        return total


async def live_debrief_task(
    ctx: dict,
    pgn: str,
    my_color: str | None = None,
    depth: int | None = None,
    max_blunders: int = 5,
    generate_puzzles: bool = True,
    explain_with_llm: bool = True,
) -> dict:
    async with SessionLocal() as session:
        report = await live_debrief(
            session, pgn_text=pgn, my_color=my_color, depth=depth,
            max_blunders=max_blunders, generate_puzzles=generate_puzzles,
            explain_with_llm=explain_with_llm,
        )
    return {
        "game_id": report.game_id,
        "moves_analyzed": report.moves_analyzed,
        "opening": report.opening,
        "phases": {k: v.__dict__ for k, v in report.phases.items()},
        "top_blunders": [b.__dict__ for b in report.top_blunders],
        "exercises_generated": report.exercises_generated,
        "elapsed_s": round(report.elapsed_s, 2),
    }


# ---------- Import / scout ----------

async def import_full_task(ctx: dict, username: str | None = None) -> dict:
    async with SessionLocal() as session:
        s = await import_full_history(session, username=username)
        return {"imported": s.imported, "skipped": s.skipped, "failed": s.failed}


async def import_month_task(ctx: dict, year: int, month: int, username: str | None = None) -> dict:
    async with SessionLocal() as session:
        s = await import_month(session, year, month, username=username)
        return {"imported": s.imported, "skipped": s.skipped, "failed": s.failed}


async def import_recent_task(ctx: dict, username: str, max_months: int = 3, max_games: int = 100) -> dict:
    async with SessionLocal() as session:
        s = await import_recent_months(session, username, max_months=max_months, max_games=max_games)
        return {"imported": s.imported, "skipped": s.skipped, "failed": s.failed}


async def import_lichess_task(ctx: dict, username: str | None = None, max_games: int = 100) -> dict:
    from app.core.config import get_settings
    from app.services.lichess_importer import import_lichess_user
    settings = get_settings()
    user = (username or settings.lichess_username or "").strip()
    if not user:
        return {"error": "LICHESS_USERNAME not configured"}
    async with SessionLocal() as session:
        s = await import_lichess_user(session, user, max_games=max_games, is_me=True)
        return {"imported": s.imported, "skipped": s.skipped, "failed": s.failed}


async def scout_task(
    ctx: dict,
    opponent_username: str,
    max_months: int = 3,
    max_games: int = 100,
    generate_plan: bool = True,
) -> dict:
    async with SessionLocal() as session:
        r = await scout_opponent(
            session, opponent_username=opponent_username,
            max_months=max_months, max_games=max_games, generate_plan=generate_plan,
        )
    return {
        "opponent": r.opponent_username,
        "games_imported": r.games_imported,
        "weaknesses": r.weaknesses[:10],
        "battle_plan": r.battle_plan,
        "elapsed_s": round(r.elapsed_s, 2),
    }


# ---------- Light, but useful in queue ----------

async def build_repertoire_task(ctx: dict) -> dict:
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        rep = await build_repertoire(session, me)
        oob = await compute_out_of_book_for_all_my_games(session, me)
        return {**rep, **oob}


async def refresh_weaknesses_task(ctx: dict) -> dict:
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        report = await refresh_player_weaknesses(session, me)
        return {
            "detectors_run": report.detectors_run,
            "findings": len(report.findings),
        }


async def generate_exercises_task(ctx: dict, min_cp_loss: int = 120) -> dict:
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        s = await generate_for_player(session, me, min_cp_loss=min_cp_loss)
        return {"inserted": s.inserted, "skipped_existing": s.skipped_existing}


async def snapshot_progress_task(ctx: dict) -> dict:
    from app.services.progress import take_snapshot
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        snap = await take_snapshot(session, me)
        return {
            "taken_at": snap.taken_at.isoformat(),
            "rating_rapid": snap.rating_rapid,
            "weaknesses_tracked": len(snap.weakness_severities or {}),
        }


async def weekly_report_task(ctx: dict, force: bool = False) -> dict:
    """Generate the weekly LLM coach report for the current player."""
    from app.services.weekly_report import generate_weekly_report
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        report = await generate_weekly_report(session, me, force=force)
        return {
            "id": report.id,
            "week_start": report.week_start.isoformat(),
            "week_end": report.week_end.isoformat(),
            "games_played": report.games_played,
            "elo_delta": report.elo_delta,
            "blunders": report.blunders_this_week,
            "has_narrative": bool(report.narrative),
        }


async def watch_live_task(ctx: dict, depth: int = 14) -> dict:
    """Poll Chess.com for newly-finished games and process them end-to-end."""
    from app.services.live_watcher import watch_once
    async with SessionLocal() as session:
        s = await watch_once(session, depth=depth)
        return {
            "games_imported": s.games_imported,
            "games_analyzed": s.games_analyzed,
            "moves_analyzed": s.moves_analyzed,
            "puzzles_generated": s.puzzles_generated,
            "new_blunders": s.new_blunders,
            "elapsed_s": round(s.elapsed_s, 1),
            "new_game_urls": s.new_game_urls[:5],
        }


async def deep_analyze_task(
    ctx: dict,
    limit: int = 50,
    depth: int = 28,
    min_cp_loss: int = 150,
    force: bool = False,
) -> dict:
    from app.services.deep_analyzer import deep_analyze_critical
    async with SessionLocal() as session:
        s = await deep_analyze_critical(
            session, limit=limit, depth=depth,
            min_cp_loss=min_cp_loss, force=force,
        )
        return {
            "moves_deep_analyzed": s.moves_deep_analyzed,
            "skipped_existing": s.skipped_existing,
            "elapsed_s": round(s.elapsed_s, 1),
        }


# Registry — order matters for the worker function list
TASK_FUNCTIONS: list[Any] = [
    analyze_game_task,
    analyze_pending_task,
    live_debrief_task,
    import_full_task,
    import_month_task,
    import_recent_task,
    import_lichess_task,
    scout_task,
    build_repertoire_task,
    refresh_weaknesses_task,
    generate_exercises_task,
    snapshot_progress_task,
    deep_analyze_task,
    watch_live_task,
    weekly_report_task,
]

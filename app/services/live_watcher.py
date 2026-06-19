"""Detect newly-finished games on Chess.com and pipeline them through
import → analyze → live debrief → puzzle generation.

Strategy:
  1. Look at the current month's archive on Chess.com.
  2. Skip games whose external_id is already in our `games` table.
  3. For each truly-new game: import (creates Move rows), analyze at a
     lower depth (default 14 — fast), and generate puzzles from blunders.
  4. Skip the LLM debrief by default (too slow for a 5-min cron). The
     user can warm it later on demand.

Stateless: idempotency comes from `external_id` UNIQUE on games — no need
for a "last_seen" pointer.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Game, Player
from app.services.analyzer import analyze_game
from app.services.chesscom import ChessComClient
from app.services.exercises.generator import generate_for_player
from app.services.openings.out_of_book import compute_out_of_book_for_game
from app.services.pgn_importer import import_chesscom_game
from app.services.stockfish import get_engine
from app.services.weakness_engine import refresh_player_weaknesses

logger = logging.getLogger(__name__)


@dataclass
class WatchStats:
    games_imported: int = 0
    games_skipped: int = 0
    games_analyzed: int = 0
    moves_analyzed: int = 0
    puzzles_generated: int = 0
    new_blunders: int = 0
    new_mistakes: int = 0
    elapsed_s: float = 0.0
    new_game_urls: list[str] = field(default_factory=list)


async def watch_once(
    session: AsyncSession,
    *,
    depth: int = 14,
    refresh_weaknesses_after: bool = True,
    months_back: int = 1,
) -> WatchStats:
    """Run one watch tick. Designed to be cheap (~few seconds when nothing new)."""
    started = time.perf_counter()
    settings = get_settings()
    me_username = settings.chesscom_username.lower()
    stats = WatchStats()

    me = (await session.execute(
        select(Player).where(Player.chesscom_username == me_username)
    )).scalar_one_or_none()
    if not me:
        logger.warning("watch_once: 'me' player %s not in DB", me_username)
        return stats

    now = datetime.now(timezone.utc)

    async with ChessComClient(username=me_username) as client:
        months: list[tuple[int, int]] = []
        for delta in range(months_back):
            ref = now.replace(day=1)
            for _ in range(delta):
                ref = (ref - __import__("datetime").timedelta(days=1)).replace(day=1)
            months.append((ref.year, ref.month))

        for year, month in months:
            try:
                games = await client.get_month_games(year, month)
            except Exception as e:
                logger.warning("Chess.com fetch %d-%02d failed: %s", year, month, e)
                continue

            for g in games:
                url = g.get("url") or g.get("uuid")
                if not url:
                    continue
                exists = await session.execute(
                    select(Game.id).where(Game.external_id == url)
                )
                if exists.scalar_one_or_none():
                    stats.games_skipped += 1
                    continue

                try:
                    game, action = await import_chesscom_game(session, g, me_username)
                except Exception as e:
                    logger.warning("import_chesscom_game failed (%s): %s", url, e)
                    continue
                if game is None or action != "imported":
                    stats.games_skipped += 1
                    continue
                stats.games_imported += 1
                stats.new_game_urls.append(url)
                await session.commit()

                # Out-of-book detection
                try:
                    await compute_out_of_book_for_game(session, game, me_player_id=me.id)
                    await session.commit()
                except Exception as e:
                    logger.warning("out-of-book failed for %s: %s", url, e)

                # Stockfish analysis (depth 14 — fast)
                try:
                    engine = await get_engine()
                    a_stats = await analyze_game(
                        session, game, engine, depth=depth, force=False,
                    )
                    stats.games_analyzed += 1
                    stats.moves_analyzed += a_stats.moves_analyzed
                    stats.new_blunders += a_stats.blunders
                    stats.new_mistakes += a_stats.mistakes
                except Exception as e:
                    logger.warning("analyze_game failed for %s: %s", url, e)
                    continue

                # Puzzles from this game's blunders
                try:
                    gen = await generate_for_player(session, me)
                    stats.puzzles_generated += gen.inserted
                except Exception as e:
                    logger.warning("generate_for_player failed: %s", e)

                # Discord/Slack notif if the game was a bloodbath
                if a_stats.blunders >= 3:
                    try:
                        from app.services.webhooks import WebhookField, WebhookMessage, notify
                        await notify(WebhookMessage(
                            title="Nouvelle partie analysée",
                            description=f"{a_stats.blunders} blunders, {a_stats.mistakes} mistakes détectés.",
                            fields=[
                                WebhookField("Coups analysés", str(a_stats.moves_analyzed), inline=True),
                                WebhookField("Inaccuracies", str(a_stats.inaccuracies), inline=True),
                                WebhookField("Puzzles générés", str(gen.inserted), inline=True),
                            ],
                            url=url,
                        ))
                    except Exception as e:
                        logger.warning("Live notify failed: %s", e)

    if refresh_weaknesses_after and stats.games_imported > 0:
        try:
            await refresh_player_weaknesses(session, me)
        except Exception as e:
            logger.warning("refresh_player_weaknesses failed: %s", e)

    stats.elapsed_s = time.perf_counter() - started
    logger.info(
        "watch_once imported=%d skipped=%d analyzed=%d blunders=%d puzzles=%d in %.1fs",
        stats.games_imported, stats.games_skipped, stats.games_analyzed,
        stats.new_blunders, stats.puzzles_generated, stats.elapsed_s,
    )
    return stats

"""High-level import orchestrator: Chess.com → DB."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.chesscom import ChessComClient
from app.services.pgn_importer import ImportStats, import_chesscom_game

logger = logging.getLogger(__name__)


async def import_month(
    session: AsyncSession, year: int, month: int, username: str | None = None
) -> ImportStats:
    settings = get_settings()
    me = (username or settings.chesscom_username).lower()
    stats = ImportStats()

    async with ChessComClient(username=me) as client:
        games = await client.get_month_games(year, month)

    for g in games:
        await _ingest_one(session, g, me, stats)

    await session.commit()
    logger.info(
        "import_month %s %d-%02d: imported=%d skipped=%d failed=%d",
        me, year, month, stats.imported, stats.skipped, stats.failed,
    )
    return stats


async def import_recent_months(
    session: AsyncSession,
    username: str,
    max_months: int = 6,
    max_games: int | None = 200,
) -> ImportStats:
    """Pull the latest `max_months` of a user's games, oldest-first within each
    month. Stops early if `max_games` reached. Used for opponent scouting.

    Note: `username` is whose games we fetch (the opponent in scout context).
    `me_username` used for is_me flagging always comes from settings — we
    never elevate an opponent to is_me.
    """
    target = username.lower()
    me_username = get_settings().chesscom_username.lower()
    stats = ImportStats()
    async with ChessComClient(username=target) as client:
        archives = await client.list_archives()
        # archives are URLs ending in /YYYY/MM — last one is the most recent
        archives = archives[-max_months:]
        for url in archives:
            # Parse year/month from URL
            try:
                ym = url.rstrip("/").split("/")[-2:]
                year, month = int(ym[0]), int(ym[1])
            except (ValueError, IndexError):
                continue
            games = await client.get_month_games(year, month)
            for g in games:
                await _ingest_one(session, g, me_username, stats)
                total_seen = stats.imported + stats.skipped + stats.failed
                if max_games and total_seen >= max_games:
                    await session.commit()
                    logger.info(
                        "import_recent_months target=%s me=%s: hit max_games=%d (imported=%d skipped=%d)",
                        target, me_username, max_games, stats.imported, stats.skipped,
                    )
                    return stats
            await session.commit()
    logger.info(
        "import_recent_months target=%s me=%s: imported=%d skipped=%d failed=%d",
        target, me_username, stats.imported, stats.skipped, stats.failed,
    )
    return stats


async def import_full_history(
    session: AsyncSession, username: str | None = None
) -> ImportStats:
    settings = get_settings()
    me = (username or settings.chesscom_username).lower()
    stats = ImportStats()

    async with ChessComClient(username=me) as client:
        async for g in client.iter_all_games():
            await _ingest_one(session, g, me, stats)
            # Commit every 50 games to bound memory/locks
            if (stats.imported + stats.skipped + stats.failed) % 50 == 0:
                await session.commit()

    await session.commit()
    logger.info(
        "import_full_history %s: imported=%d skipped=%d failed=%d",
        me, stats.imported, stats.skipped, stats.failed,
    )
    return stats


async def _ingest_one(
    session: AsyncSession,
    game: dict[str, Any],
    me_username: str,
    stats: ImportStats,
) -> None:
    try:
        _, action = await import_chesscom_game(session, game, me_username)
    except Exception as e:
        stats.failed += 1
        stats.errors.append(f"{game.get('url', '?')}: {e}")
        await session.rollback()
        return
    if action == "imported":
        stats.imported += 1
    elif action == "updated":
        stats.updated += 1
    elif action == "skipped":
        stats.skipped += 1
    else:
        stats.failed += 1

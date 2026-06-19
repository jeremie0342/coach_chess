"""Arq worker settings — entry point: `uv run arq app.worker.settings.WorkerSettings`."""
from __future__ import annotations

import logging

from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import get_settings
from app.services.stockfish import shutdown_engine
from app.worker.tasks import (
    TASK_FUNCTIONS,
    refresh_weaknesses_task,
    snapshot_progress_task,
    watch_live_task,
    weekly_report_task,
)

logger = logging.getLogger(__name__)


def _redis_settings() -> RedisSettings:
    from urllib.parse import urlparse
    url = get_settings().redis_url
    p = urlparse(url)
    return RedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        database=int((p.path or "/0").lstrip("/") or 0),
        password=p.password,
    )


async def on_startup(ctx: dict) -> None:
    logger.info("arq worker starting (%d functions registered)", len(TASK_FUNCTIONS))


async def on_shutdown(ctx: dict) -> None:
    await shutdown_engine()
    logger.info("arq worker stopped")


# Scheduled jobs (arq cron). Times are UTC.
CRON_JOBS = [
    # Watch Chess.com for new games every 5 minutes
    cron(
        watch_live_task,
        minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
        run_at_startup=False,
        unique=True,
    ),
    # Take a metric snapshot every day at 23:00 UTC
    cron(
        snapshot_progress_task,
        hour={23}, minute={0},
        run_at_startup=False,
        unique=True,
    ),
    # Refresh weaknesses once a day at 22:30 UTC, before snapshot
    cron(
        refresh_weaknesses_task,
        hour={22}, minute={30},
        run_at_startup=False,
        unique=True,
    ),
    # Weekly LLM coach report — Sunday 18:00 UTC
    cron(
        weekly_report_task,
        weekday={6},  # Sunday in arq's 0=Mon..6=Sun (Python's weekday() convention)
        hour={18}, minute={0},
        run_at_startup=False,
        unique=True,
    ),
]


class WorkerSettings:
    functions = TASK_FUNCTIONS
    cron_jobs = CRON_JOBS
    redis_settings = _redis_settings()
    on_startup = on_startup
    on_shutdown = on_shutdown
    job_timeout = 6 * 3600
    keep_result = 7 * 24 * 3600
    max_jobs = 4
    poll_delay = 0.5

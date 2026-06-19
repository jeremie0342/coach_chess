"""Build and (optionally) push a Lichess Study from your games.

Two modes:

  1. **Local file** — concatenate annotated PGNs of selected games into one
     `.pgn` file. Upload manually to Lichess via the "Import PGN" button on
     any study page. No auth needed.

  2. **API push** — POST to /api/study/{studyId}/import-pgn with each game
     as a chapter. Requires a Lichess token with the `study:write` scope.

Lichess study limits: a study can hold up to ~64 chapters. We respect that.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Game, Player
from app.services.pgn_exporter import ExportOptions, export_annotated_pgn

logger = logging.getLogger(__name__)


LICHESS_API_BASE = "https://lichess.org"
MAX_CHAPTERS_PER_PUSH = 32     # well under the 64-limit; safer for first try


@dataclass
class StudyPushStats:
    chapters_pushed: int = 0
    chapters_failed: int = 0
    bytes_sent: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


async def _select_games(
    session: AsyncSession,
    player: Player,
    *,
    eco: str | None = None,
    color: str | None = None,             # "white" | "black"
    only_with_analysis: bool = True,
    only_losses: bool = False,
    limit: int = 20,
) -> list[Game]:
    q = select(Game).where(
        or_(Game.white_player_id == player.id, Game.black_player_id == player.id)
    )
    if eco:
        q = q.where(Game.eco == eco)
    if color == "white":
        q = q.where(Game.white_player_id == player.id)
    elif color == "black":
        q = q.where(Game.black_player_id == player.id)
    if only_with_analysis:
        q = q.where(Game.analysis_status == "done")
    if only_losses:
        from app.models.game import GameResult
        from sqlalchemy import case
        q = q.where(case(
            ((Game.white_player_id == player.id) & (Game.result == GameResult.BLACK_WIN), True),
            ((Game.black_player_id == player.id) & (Game.result == GameResult.WHITE_WIN), True),
            else_=False,
        ))
    q = q.order_by(Game.played_at.desc()).limit(limit)
    return list((await session.execute(q)).scalars())


async def build_pgn_bundle(
    session: AsyncSession,
    player: Player,
    *,
    eco: str | None = None,
    color: str | None = None,
    only_with_analysis: bool = True,
    only_losses: bool = False,
    limit: int = 20,
    include_llm: bool = False,
) -> tuple[str, list[Game]]:
    """Return a multi-game PGN string + the list of Game rows included."""
    games = await _select_games(
        session, player, eco=eco, color=color,
        only_with_analysis=only_with_analysis,
        only_losses=only_losses, limit=limit,
    )
    opts = ExportOptions(include_llm=include_llm, llm_only_worst=5)
    pgns: list[str] = []
    for g in games:
        try:
            pgn = await export_annotated_pgn(session, g, opts)
            if pgn.strip():
                pgns.append(pgn.strip())
        except Exception as e:
            logger.warning("PGN export failed for game %d: %s", g.id, e)
    return "\n\n".join(pgns), games


async def push_to_study(
    session: AsyncSession,
    player: Player,
    study_id: str,
    *,
    eco: str | None = None,
    color: str | None = None,
    only_losses: bool = False,
    limit: int = 20,
    include_llm: bool = False,
) -> StudyPushStats:
    """Push N annotated games as chapters into an existing Lichess study.

    Requires a Lichess token with study:write scope, set in `.env` as
    `LICHESS_TOKEN`. We post each chapter sequentially (chapter creation is
    cheap; the API accepts one PGN per call).
    """
    settings = get_settings()
    token = settings.lichess_token
    if not token:
        raise RuntimeError(
            "LICHESS_TOKEN not set. Generate one at "
            "https://lichess.org/account/oauth/token with study:write scope."
        )
    limit = min(limit, MAX_CHAPTERS_PER_PUSH)
    games = await _select_games(
        session, player, eco=eco, color=color,
        only_with_analysis=True, only_losses=only_losses, limit=limit,
    )
    stats = StudyPushStats()

    opts = ExportOptions(include_llm=include_llm, llm_only_worst=5)
    async with httpx.AsyncClient(
        base_url=LICHESS_API_BASE,
        timeout=httpx.Timeout(30.0, connect=5.0),
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "coach_chess/0.1",
        },
    ) as client:
        for g in games:
            try:
                pgn = await export_annotated_pgn(session, g, opts)
                if not pgn.strip():
                    continue
                chapter_name = _chapter_name(g)
                resp = await client.post(
                    f"/api/study/{study_id}/import-pgn",
                    data={
                        "name": chapter_name,
                        "pgn": pgn,
                        "variant": "standard",
                        "orientation": "white" if g.white_player_id == player.id else "black",
                    },
                )
                if resp.status_code >= 400:
                    stats.chapters_failed += 1
                    stats.errors.append(f"game#{g.id}: HTTP {resp.status_code} {resp.text[:120]}")
                    continue
                stats.chapters_pushed += 1
                stats.bytes_sent += len(pgn.encode("utf-8"))
            except Exception as e:
                stats.chapters_failed += 1
                stats.errors.append(f"game#{g.id}: {type(e).__name__}: {e}")
    return stats


def _chapter_name(game: Game) -> str:
    from datetime import datetime
    bits = []
    if game.played_at:
        bits.append(game.played_at.strftime("%Y-%m-%d"))
    if game.eco:
        bits.append(game.eco)
    if game.opening_name:
        bits.append(game.opening_name[:60])
    bits.append(f"#{game.id}")
    return " · ".join(bits)

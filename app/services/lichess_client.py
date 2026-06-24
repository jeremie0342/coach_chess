"""Thin async client for the Lichess public API.

Lichess exposes two APIs we need:
  - /api/games/user/{username}  (NDJSON streaming, all games of a user)
  - /api/user/{username}        (profile + perfs)

Anonymous calls work but are rate-limited (~60 req/min). Authenticated calls
get a much higher quota — we pass the LICHESS_TOKEN from .env when present.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

LICHESS_BASE = "https://lichess.org"


@dataclass
class LichessClient:
    username: str
    token: str | None = None

    def __post_init__(self) -> None:
        if self.token is None:
            self.token = get_settings().lichess_token

    def _headers(self) -> dict[str, str]:
        h = {
            "User-Agent": "coach_chess/0.1",
            # Streaming endpoint defaults to NDJSON but we make it explicit
            "Accept": "application/x-ndjson",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def __aenter__(self) -> "LichessClient":
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))
        return self

    async def __aexit__(self, *_exc) -> None:
        await self._client.aclose()

    async def stream_games(
        self,
        *,
        max_games: int = 100,
        since: datetime | None = None,
        until: datetime | None = None,
        rated: bool | None = None,
    ) -> AsyncIterator[dict]:
        """Yield Lichess games as dicts in reverse-chronological order
        (newest first). Each dict has the raw Lichess JSON shape plus the
        full PGN text under `pgn` (we set `pgnInJson=true`).
        """
        params: dict[str, str] = {
            "max": str(max_games),
            "pgnInJson": "true",
            "clocks": "true",
            "tags": "true",
            "opening": "true",
            "moves": "false",   # we re-walk via python-chess from the PGN
            "evals": "false",
        }
        if since is not None:
            params["since"] = str(int(since.replace(tzinfo=timezone.utc).timestamp() * 1000))
        if until is not None:
            params["until"] = str(int(until.replace(tzinfo=timezone.utc).timestamp() * 1000))
        if rated is not None:
            params["rated"] = "true" if rated else "false"

        url = f"{LICHESS_BASE}/api/games/user/{self.username}"
        async with self._client.stream("GET", url, params=params, headers=self._headers()) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning("Lichess NDJSON parse failed: %s", e)
                    continue

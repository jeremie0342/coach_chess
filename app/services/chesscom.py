"""Chess.com public API client.

Docs: https://www.chess.com/news/view/published-data-api

Chess.com requires a meaningful User-Agent (with contact info). They block
generic clients. We send a custom one identifying this app.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import get_settings


class ChessComClient:
    def __init__(self, username: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self.username = (username or settings.chesscom_username).lower()
        self.base_url = (base_url or settings.chesscom_base_url).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            headers={
                "User-Agent": "coach_chess/0.1 (self-hosted personal chess coach)",
                "Accept": "application/json",
            },
        )

    async def __aenter__(self) -> "ChessComClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def get_player(self) -> dict[str, Any]:
        r = await self._client.get(f"/player/{self.username}")
        r.raise_for_status()
        return r.json()

    async def list_archives(self) -> list[str]:
        """Return list of monthly archive URLs (one per month the user played)."""
        r = await self._client.get(f"/player/{self.username}/games/archives")
        r.raise_for_status()
        return r.json().get("archives", [])

    async def get_month_games(self, year: int, month: int) -> list[dict[str, Any]]:
        r = await self._client.get(
            f"/player/{self.username}/games/{year:04d}/{month:02d}"
        )
        r.raise_for_status()
        return r.json().get("games", [])

    async def iter_all_games(self) -> AsyncIterator[dict[str, Any]]:
        """Yield every game across every month, oldest first."""
        for url in await self.list_archives():
            # url ends with /YYYY/MM — pull directly with full URL
            r = await self._client.get(url)
            r.raise_for_status()
            for game in r.json().get("games", []):
                yield game

"""Thin async client around the Lichess opening explorer.

Endpoints used:
  GET https://explorer.lichess.ovh/masters?fen=... &moves=12 &topGames=4
  GET https://explorer.lichess.ovh/lichess?fen=...
        &speeds=blitz,rapid,classical
        &ratings=2000,2200,2500
        &moves=12 &topGames=0

Both return JSON like:
  {
    "white": int, "draws": int, "black": int,
    "moves": [
      {"uci": "e2e4", "san": "e4",
       "white": int, "draws": int, "black": int,
       "averageRating": int, "averageOpponentRating": int},
      ...
    ],
    "topGames": [{...}]
  }

Rate limits:
  /masters  : ~50 requests / minute
  /lichess  : ~200 requests / minute

We add a small disk cache (one JSON per fen-epd) so repeated lookups are
instant.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import chess
import httpx

from app.core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


CACHE_DIR = PROJECT_ROOT / "data" / "explorer_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

EXPLORER_BASE = "https://explorer.lichess.ovh"


@dataclass
class ExplorerMove:
    uci: str
    san: str
    white: int
    draws: int
    black: int
    games: int
    avg_rating: int | None
    winrate_white: float
    winrate_black: float
    score_white: float   # (white + 0.5*draws) / games

    @classmethod
    def from_dict(cls, d: dict) -> "ExplorerMove":
        w, dr, b = d.get("white", 0), d.get("draws", 0), d.get("black", 0)
        n = max(w + dr + b, 1)
        return cls(
            uci=d.get("uci", ""), san=d.get("san", ""),
            white=w, draws=dr, black=b, games=n,
            avg_rating=d.get("averageRating"),
            winrate_white=w / n, winrate_black=b / n,
            score_white=(w + 0.5 * dr) / n,
        )


@dataclass
class ExplorerResult:
    db: str
    fen_epd: str
    total_games: int
    white: int
    draws: int
    black: int
    moves: list[ExplorerMove]

    def best_move_for(self, color: Literal["white", "black"]) -> ExplorerMove | None:
        if not self.moves:
            return None
        if color == "white":
            return max(self.moves, key=lambda m: m.score_white)
        return max(self.moves, key=lambda m: 1 - m.score_white)


def _cache_path(db: str, epd: str, ratings: str | None, speeds: str | None) -> Path:
    key = f"{db}|{epd}|{ratings or ''}|{speeds or ''}"
    h = hashlib.sha1(key.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{db}_{h}.json"


def _fen_to_epd(fen: str) -> str:
    return chess.Board(fen).epd()


class ExplorerClient:
    def __init__(self) -> None:
        from app.core.config import get_settings
        headers = {
            "User-Agent": "coach_chess/0.1 (personal opening explorer)",
            "Accept": "application/json",
        }
        token = get_settings().lichess_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=EXPLORER_BASE,
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers=headers,
        )
        # Naive throttle: enforce min delay between requests
        self._last_req: dict[str, float] = {"masters": 0.0, "lichess": 0.0}
        self._min_interval = {"masters": 1.3, "lichess": 0.35}
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "ExplorerClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _throttle(self, db: str) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_req[db]
            wait = self._min_interval[db] - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_req[db] = asyncio.get_event_loop().time()

    async def query(
        self,
        fen: str,
        db: Literal["masters", "lichess"] = "masters",
        ratings: str | None = "2000,2200,2500",
        speeds: str | None = "blitz,rapid,classical",
        moves: int = 12,
        top_games: int = 0,
        use_cache: bool = True,
    ) -> ExplorerResult:
        epd = _fen_to_epd(fen)
        cache_file = _cache_path(db, epd, ratings if db == "lichess" else None,
                                  speeds if db == "lichess" else None)
        if use_cache and cache_file.exists():
            try:
                with cache_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                return _parse_result(db, epd, data)
            except Exception:
                pass

        params: dict[str, str | int] = {"fen": fen, "moves": moves, "topGames": top_games}
        if db == "lichess":
            if ratings:
                params["ratings"] = ratings
            if speeds:
                params["speeds"] = speeds

        await self._throttle(db)
        r = await self._client.get(f"/{db}", params=params)
        if r.status_code == 429:
            # Lichess told us to slow down; back off briefly and retry once
            await asyncio.sleep(2.0)
            r = await self._client.get(f"/{db}", params=params)
        r.raise_for_status()
        data = r.json()
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return _parse_result(db, epd, data)


def _parse_result(db: str, epd: str, data: dict) -> ExplorerResult:
    w, dr, b = data.get("white", 0), data.get("draws", 0), data.get("black", 0)
    moves = [ExplorerMove.from_dict(m) for m in data.get("moves", [])]
    return ExplorerResult(
        db=db, fen_epd=epd, total_games=w + dr + b,
        white=w, draws=dr, black=b, moves=moves,
    )

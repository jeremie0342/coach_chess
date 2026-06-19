"""Syzygy endgame tablebase access.

Two backends, in priority order:

  1. **Local Syzygy files** under `data/syzygy/` — fastest, offline.
     python-chess opens them via `chess.syzygy.Tablebase`.
  2. **Lichess Tablebase API** — free, public, no auth.
     GET https://tablebase.lichess.ovh/standard?fen=...
     Returns: { category: win|draw|loss|cursed-win|blessed-loss|unknown, wdl, dtz, dtm }

Probe returns None for both wdl and dtz if neither backend resolves.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import chess
import chess.syzygy
import httpx

from app.core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


TB_DIR = PROJECT_ROOT / "data" / "syzygy"
LICHESS_TB_BASE = "https://tablebase.lichess.ovh"


@dataclass
class TablebaseProbe:
    fen: str
    pieces: int
    wdl: int | None        # +2/+1 win, 0 draw, -1/-2 loss
    dtz: int | None
    verdict: Literal["win", "draw", "loss", "unknown"]
    source: Literal["local", "lichess", "none"]


_TB: chess.syzygy.Tablebase | None = None


def _local_tablebase() -> chess.syzygy.Tablebase | None:
    global _TB
    if _TB is not None:
        return _TB
    TB_DIR.mkdir(parents=True, exist_ok=True)
    if not any(TB_DIR.glob("*.rtbw")):
        return None
    try:
        _TB = chess.syzygy.open_tablebase(str(TB_DIR), max_fds=64)
        return _TB
    except Exception as e:
        logger.warning("Failed to open local syzygy tables: %s", e)
        return None


def _verdict_from_category(cat: str | None) -> Literal["win", "draw", "loss", "unknown"]:
    if cat in ("win", "cursed-win", "maybe-win"):
        return "win"
    if cat in ("loss", "blessed-loss", "maybe-loss"):
        return "loss"
    if cat == "draw":
        return "draw"
    return "unknown"


def _verdict_from_wdl(wdl: int | None) -> Literal["win", "draw", "loss", "unknown"]:
    if wdl is None:
        return "unknown"
    if wdl >= 1:
        return "win"
    if wdl <= -1:
        return "loss"
    return "draw"


def probe_local(fen: str) -> TablebaseProbe | None:
    board = chess.Board(fen)
    pieces = chess.popcount(board.occupied)
    tb = _local_tablebase()
    if tb is None or pieces > 7:
        return None
    try:
        wdl = tb.probe_wdl(board)
        dtz = tb.probe_dtz(board)
    except chess.syzygy.MissingTableError:
        return None
    except Exception as e:
        logger.warning("local probe failed (%s): %s", fen, e)
        return None
    return TablebaseProbe(
        fen=fen, pieces=pieces, wdl=wdl, dtz=dtz,
        verdict=_verdict_from_wdl(wdl), source="local",
    )


async def probe_lichess(fen: str) -> TablebaseProbe | None:
    board = chess.Board(fen)
    pieces = chess.popcount(board.occupied)
    if pieces > 7:
        return None
    try:
        async with httpx.AsyncClient(
            base_url=LICHESS_TB_BASE,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": "coach_chess/0.1"},
        ) as client:
            r = await client.get("/standard", params={"fen": fen})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("lichess tablebase probe failed (%s): %s", fen, e)
        return None
    cat = data.get("category")
    wdl = data.get("wdl")
    dtz = data.get("dtz")
    return TablebaseProbe(
        fen=fen, pieces=pieces, wdl=wdl, dtz=dtz,
        verdict=_verdict_from_category(cat), source="lichess",
    )


async def probe(fen: str) -> TablebaseProbe:
    local = probe_local(fen)
    if local is not None:
        return local
    remote = await probe_lichess(fen)
    if remote is not None:
        return remote
    board = chess.Board(fen)
    return TablebaseProbe(
        fen=fen, pieces=chess.popcount(board.occupied),
        wdl=None, dtz=None, verdict="unknown", source="none",
    )


def has_local_tables() -> bool:
    return _local_tablebase() is not None

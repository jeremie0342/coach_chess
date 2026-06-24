"""Stockfish service — sync SimpleEngine wrapped in a thread pool.

We use python-chess's SimpleEngine (regular subprocess.Popen) instead of the
async popen_uci, because on Windows uvicorn often runs on SelectorEventLoop
which does not support asyncio.subprocess_exec. Sync calls are dispatched via
asyncio.to_thread so callers stay async.

Engine processes are not free — we hold a singleton instance protected by an
asyncio.Lock to serialise access (SimpleEngine is not thread-safe across
concurrent analyse() calls). The /health endpoint uses ping_engine() for a
cheap probe that spawns a throwaway engine.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import chess
import chess.engine

from app.core.config import get_settings


@dataclass
class EngineInfo:
    name: str
    author: str | None
    options: list[str]


_engine_lock = asyncio.Lock()
_engine: chess.engine.SimpleEngine | None = None


def _spawn_engine_sync() -> chess.engine.SimpleEngine:
    settings = get_settings()
    sf_path = str(settings.stockfish_abs_path)
    eng = chess.engine.SimpleEngine.popen_uci(sf_path)
    eng.configure(
        {
            "Threads": settings.stockfish_threads,
            "Hash": settings.stockfish_hash_mb,
        }
    )
    return eng


async def get_engine() -> chess.engine.SimpleEngine:
    global _engine
    async with _engine_lock:
        if _engine is None:
            _engine = await asyncio.to_thread(_spawn_engine_sync)
        return _engine


async def shutdown_engine() -> None:
    global _engine
    async with _engine_lock:
        if _engine is not None:
            try:
                await asyncio.to_thread(_engine.quit)
            except Exception:
                pass
            _engine = None


async def ping_engine() -> EngineInfo:
    """Spawn-and-kill probe — does not touch the cached singleton."""
    eng = await asyncio.to_thread(_spawn_engine_sync)
    try:
        return EngineInfo(
            name=eng.id.get("name", "unknown"),
            author=eng.id.get("author"),
            options=list(eng.options.keys())[:8],
        )
    finally:
        try:
            await asyncio.to_thread(eng.quit)
        except Exception:
            pass


async def analyse_fen(
    fen: str,
    depth: int | None = None,
    multipv: int = 1,
) -> list[dict]:
    """Run Stockfish on a FEN and return MultiPV results."""
    settings = get_settings()
    board = chess.Board(fen)
    engine = await get_engine()
    # SimpleEngine is not safe for concurrent analyse() — serialise.
    async with _engine_lock:
        info = await asyncio.to_thread(
            engine.analyse,
            board,
            chess.engine.Limit(depth=depth or settings.stockfish_default_depth),
            multipv=multipv,
        )
    if isinstance(info, dict):
        info = [info]
    results = []
    for line in info:
        score = line["score"].pov(board.turn)
        results.append(
            {
                "depth": line.get("depth"),
                "eval_cp": score.score(mate_score=100000) if not score.is_mate() else None,
                "eval_mate": score.mate() if score.is_mate() else None,
                "pv_uci": [m.uci() for m in line.get("pv", [])],
                "pv_san": board.variation_san(line.get("pv", [])) if line.get("pv") else None,
            }
        )
    return results

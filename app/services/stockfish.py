"""Async wrapper around Stockfish via python-chess UCI engine.

This is a thin service the rest of the app will use for analysis.
Engine processes are not free — callers should reuse the singleton via
get_engine(). The /health endpoint uses ping_engine() for a cheap probe.
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
_engine: chess.engine.UciProtocol | None = None
_transport: asyncio.SubprocessTransport | None = None


async def _spawn_engine() -> tuple[asyncio.SubprocessTransport, chess.engine.UciProtocol]:
    settings = get_settings()
    sf_path = str(settings.stockfish_abs_path)
    transport, engine = await chess.engine.popen_uci(sf_path)
    await engine.configure(
        {
            "Threads": settings.stockfish_threads,
            "Hash": settings.stockfish_hash_mb,
        }
    )
    return transport, engine


async def get_engine() -> chess.engine.UciProtocol:
    global _engine, _transport
    async with _engine_lock:
        if _engine is None:
            _transport, _engine = await _spawn_engine()
        return _engine


async def shutdown_engine() -> None:
    global _engine, _transport
    async with _engine_lock:
        if _engine is not None:
            try:
                await _engine.quit()
            except Exception:
                pass
            _engine = None
            _transport = None


async def ping_engine() -> EngineInfo:
    """Spawn-and-kill probe — does not touch the cached singleton.

    Used by /health to confirm the binary is reachable without forcing
    the long-lived engine to start at boot time.
    """
    settings = get_settings()
    transport, engine = await chess.engine.popen_uci(str(settings.stockfish_abs_path))
    try:
        return EngineInfo(
            name=engine.id.get("name", "unknown"),
            author=engine.id.get("author"),
            options=list(engine.options.keys())[:8],
        )
    finally:
        await engine.quit()


async def analyse_fen(
    fen: str,
    depth: int | None = None,
    multipv: int = 1,
) -> list[dict]:
    """Run Stockfish on a FEN and return MultiPV results."""
    settings = get_settings()
    board = chess.Board(fen)
    engine = await get_engine()
    info = await engine.analyse(
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

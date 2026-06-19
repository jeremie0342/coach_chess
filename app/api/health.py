from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine as db_engine
from app.services.stockfish import ping_engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    started = time.perf_counter()
    status: dict[str, Any] = {"status": "ok", "checks": {}}

    # --- Database ---
    db_started = time.perf_counter()
    try:
        async with db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status["checks"]["database"] = {
            "ok": True,
            "latency_ms": round((time.perf_counter() - db_started) * 1000, 2),
        }
    except Exception as e:
        status["status"] = "degraded"
        status["checks"]["database"] = {"ok": False, "error": str(e)}

    # --- Stockfish ---
    sf_started = time.perf_counter()
    try:
        info = await ping_engine()
        status["checks"]["stockfish"] = {
            "ok": True,
            "name": info.name,
            "author": info.author,
            "latency_ms": round((time.perf_counter() - sf_started) * 1000, 2),
        }
    except Exception as e:
        status["status"] = "degraded"
        status["checks"]["stockfish"] = {"ok": False, "error": str(e)}

    # --- Chess.com (cheap, public) ---
    cc_started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.chesscom_base_url}/player/{settings.chesscom_username}"
            )
            status["checks"]["chesscom"] = {
                "ok": r.status_code == 200,
                "username": settings.chesscom_username,
                "status_code": r.status_code,
                "latency_ms": round((time.perf_counter() - cc_started) * 1000, 2),
            }
            if r.status_code != 200:
                status["status"] = "degraded"
    except Exception as e:
        status["status"] = "degraded"
        status["checks"]["chesscom"] = {"ok": False, "error": str(e)}

    # --- Ollama (optional, not fatal if down) ---
    ol_started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            status["checks"]["ollama"] = {
                "ok": r.status_code == 200,
                "status_code": r.status_code,
                "latency_ms": round((time.perf_counter() - ol_started) * 1000, 2),
            }
    except Exception as e:
        status["checks"]["ollama"] = {"ok": False, "error": str(e), "note": "optional"}

    status["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return status

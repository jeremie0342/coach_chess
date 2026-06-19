"""Print the up/down status of every stack component.

Usage:
    uv run python scripts/coach_status.py
"""
from __future__ import annotations

import asyncio
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import text

from app.core.config import get_settings


def _tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _label(ok: bool, name: str, detail: str = "") -> None:
    tag = "  [OK]  " if ok else "  [FAIL]"
    color = "\033[32m" if ok else "\033[31m"
    reset = "\033[0m"
    print(f"{color}{tag}{reset} {name:<14} {detail}")


async def main() -> int:
    settings = get_settings()
    print("\n=== coach_chess stack status ===\n")

    # 1. Postgres
    t0 = time.perf_counter()
    pg_ok = _tcp_open("127.0.0.1", 5432)
    _label(pg_ok, "Postgres", f"127.0.0.1:5432 ({(time.perf_counter() - t0) * 1000:.0f}ms)")
    if pg_ok:
        try:
            from app.db.session import engine
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            _label(True, "  pg query", "SELECT 1 ok")
        except Exception as e:
            _label(False, "  pg query", str(e)[:80])

    # 2. Memurai (Redis)
    redis_ok = _tcp_open("127.0.0.1", 6379)
    _label(redis_ok, "Memurai/Redis", "127.0.0.1:6379")

    # 3. Stockfish
    sf = settings.stockfish_abs_path
    sf_ok = sf.exists()
    _label(sf_ok, "Stockfish", f"{sf.name}" if sf_ok else f"missing: {sf}")

    # 4. Ollama
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
        ok = r.status_code == 200
        models = r.json().get("models", []) if ok else []
        _label(ok, "Ollama", f"{len(models)} models" if ok else f"HTTP {r.status_code}")
    except Exception as e:
        _label(False, "Ollama", str(e)[:80])

    # 5. FastAPI (might not be running)
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get("http://127.0.0.1:8765/health")
        ok = r.status_code == 200
        _label(ok, "FastAPI", "http://127.0.0.1:8765" if ok else f"HTTP {r.status_code}")
    except Exception:
        _label(False, "FastAPI", "not running on :8765 (run start.ps1)")

    # 6. Arq worker (no direct probe; check Redis for arq:queue key)
    try:
        import redis.asyncio as redis_async
        r_client = redis_async.from_url(settings.redis_url)
        keys = await r_client.keys("arq:*")
        await r_client.aclose()
        _label(bool(keys), "Arq worker", f"{len(keys)} arq keys in Redis" if keys else "no arq state — worker likely down")
    except Exception as e:
        _label(False, "Arq worker", str(e)[:80])

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

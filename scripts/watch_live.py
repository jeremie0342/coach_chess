"""Manual one-shot live watcher (in addition to the cron schedule).

Usage:
    uv run python scripts/watch_live.py             # default depth 14
    uv run python scripts/watch_live.py --depth 18  # slower but more thorough
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.live_watcher import watch_once
from app.services.stockfish import shutdown_engine


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        s = await watch_once(session, depth=args.depth, months_back=args.months_back)
    print(
        f"\nimported={s.games_imported} skipped={s.games_skipped} "
        f"analyzed={s.games_analyzed} moves={s.moves_analyzed}\n"
        f"new blunders={s.new_blunders} new mistakes={s.new_mistakes} "
        f"puzzles={s.puzzles_generated}\n"
        f"elapsed: {s.elapsed_s:.1f}s"
    )
    if s.new_game_urls:
        print("New games:")
        for u in s.new_game_urls:
            print(f"  - {u}")
    await shutdown_engine()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--depth", type=int, default=14)
    p.add_argument("--months-back", type=int, default=1,
                   help="How many recent months to scan (default 1 = current month)")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

"""Re-analyze the player's worst N blunders at high Stockfish depth.

Usage:
    uv run python scripts/deep_analyze.py                  # default: 20 worst, depth 28
    uv run python scripts/deep_analyze.py --limit 50 --depth 26
    uv run python scripts/deep_analyze.py --force          # re-deep already-deep moves
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.deep_analyzer import deep_analyze_critical
from app.services.stockfish import shutdown_engine


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        stats = await deep_analyze_critical(
            session,
            limit=args.limit,
            depth=args.depth,
            min_cp_loss=args.min_cp_loss,
            force=args.force,
        )
    print(
        f"\nDeep-analyzed {stats.moves_deep_analyzed} moves "
        f"(skipped existing: {stats.skipped_existing}) in {stats.elapsed_s:.1f}s "
        f"at depth {args.depth}."
    )
    await shutdown_engine()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--depth", type=int, default=28)
    p.add_argument("--min-cp-loss", type=int, default=150)
    p.add_argument("--force", action="store_true")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

"""Annotate your repertoire nodes with Lichess masters DB frequencies.

Usage:
    uv run python scripts/annotate_repertoire.py                # 50 nodes, skip already-done
    uv run python scripts/annotate_repertoire.py --limit 200    # more in one run
    uv run python scripts/annotate_repertoire.py --force        # refresh all
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.repertoire_annotator import annotate_repertoire


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        stats = await annotate_repertoire(
            session, limit=args.limit, skip_existing=not args.force,
        )
    print(
        f"\nAnnotated: {stats.annotated}  "
        f"no-data: {stats.skipped_no_data}  "
        f"skipped: {stats.skipped_existing}  "
        f"failed: {stats.failed}  "
        f"in {stats.elapsed_s:.1f}s"
    )
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--force", action="store_true")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

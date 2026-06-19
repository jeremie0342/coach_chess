"""Generate puzzles from your analyzed blunders.

Idempotent — running it again as more games get analyzed just adds new
puzzles for the newly-detected mistakes.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Player
from app.services.exercises.generator import generate_for_player


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
        if not me:
            print("No 'is_me' player.")
            return 1
        stats = await generate_for_player(session, me, min_cp_loss=args.min_cp_loss)
        print(f"\nExercises generated:")
        print(f"  inserted        : {stats.inserted}")
        print(f"  already existed : {stats.skipped_existing}")
        print(f"  no best move    : {stats.skipped_no_best}")
        print(f"  failed          : {stats.failed}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--min-cp-loss", type=int, default=120,
                   help="Only blunders losing at least this many centipawns")
    args = p.parse_args()
    raise SystemExit(asyncio.run(amain(args)))

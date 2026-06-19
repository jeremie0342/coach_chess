"""Diagnose analysis state."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import func, select
from app.db.session import SessionLocal
from app.models import Game


async def main() -> int:
    async with SessionLocal() as s:
        # Total games + breakdown by status
        rows = (await s.execute(
            select(Game.analysis_status, func.count(Game.id))
            .group_by(Game.analysis_status)
        )).all()
        print("=== analysis_status breakdown ===")
        for status, n in rows:
            print(f"  {status:>10}: {n}")
        total = (await s.execute(select(func.count(Game.id)))).scalar_one()
        print(f"  {'TOTAL':>10}: {total}")

        # Game IDs marked done with analyzed_at
        done = (await s.execute(
            select(func.count(Game.id))
            .where(Game.analysis_status == "done")
            .where(Game.analyzed_at.is_not(None))
        )).scalar_one()
        print(f"\nGames truly done (status=done AND analyzed_at NOT NULL): {done}")

        # Range of game IDs that are done
        first_done = (await s.execute(
            select(func.min(Game.id)).where(Game.analysis_status == "done")
        )).scalar()
        last_done = (await s.execute(
            select(func.max(Game.id)).where(Game.analysis_status == "done")
        )).scalar()
        print(f"Done game IDs range: {first_done} .. {last_done}")

        # Recent 100 games and their status
        recent_q = (await s.execute(
            select(Game.id, Game.analysis_status, Game.analyzed_at)
            .order_by(Game.played_at.desc())
            .limit(100)
        )).all()
        n_recent_done = sum(1 for _, st, _ in recent_q if st == "done")
        n_recent_pending = sum(1 for _, st, _ in recent_q if st == "pending")
        print(f"\nOf the 100 most recent games (by played_at):")
        print(f"  done    : {n_recent_done}")
        print(f"  pending : {n_recent_pending}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

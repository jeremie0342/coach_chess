"""Slice your blunder rate by opponent strength, phase, clock, time of day."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Player
from app.services.contextual_patterns import analyse_context


async def main() -> int:
    async with SessionLocal() as s:
        me = (await s.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        r = await analyse_context(s, me)
    print(f"\n=== Contextual blunder patterns — {me.chesscom_username} ===")
    print(f"Baseline blunder rate: {r.baseline_blunder_rate * 100:.2f}%  over {r.total_moves:,} moves")
    if not r.insights:
        print("(not enough data — keep playing/analyzing)")
        return 0
    print()
    for ins in r.insights:
        if not ins.comment:
            continue
        arrow = "↑" if ins.relative_to_baseline > 1 else "↓"
        print(f"  {arrow} {ins.metric:>18} = {ins.bucket:<15}  "
              f"rate={ins.blunder_rate * 100:5.2f}%  "
              f"({ins.relative_to_baseline:>4.2f}× baseline)  "
              f"n={ins.sample_moves}")
        print(f"     {ins.comment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

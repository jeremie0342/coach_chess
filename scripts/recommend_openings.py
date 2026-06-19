"""Recommend openings to learn based on your style + current record."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Player
from app.services.opening_recommendation import recommend


async def main() -> int:
    async with SessionLocal() as s:
        me = (await s.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        recs = await recommend(s, me, top_n=6)
    print(f"\n=== Opening recommendations for {me.chesscom_username} ===\n")
    for i, r in enumerate(recs, start=1):
        print(f"{i}. {r.name}  [{r.eco}, {r.color}]   fit={r.fit_score}")
        print(f"   Role : {r.role}")
        print(f"   Why  : {r.short_pitch}")
        if r.rationale:
            print(f"   Note : {r.rationale}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

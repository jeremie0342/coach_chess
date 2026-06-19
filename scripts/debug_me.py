"""Find duplicate is_me rows."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Player


async def main() -> int:
    async with SessionLocal() as s:
        rows = list((await s.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalars())
        print(f"Players with is_me=True: {len(rows)}")
        for r in rows:
            print(f"  id={r.id}  username={r.chesscom_username}  created={r.created_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

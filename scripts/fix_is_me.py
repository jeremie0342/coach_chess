"""Repair: only one player should have is_me=True (settings.chesscom_username)."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, update
from app.db.session import SessionLocal
from app.models import Player
from app.core.config import get_settings


async def main() -> int:
    me_username = get_settings().chesscom_username.lower()
    async with SessionLocal() as s:
        rows = list((await s.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalars())
        print(f"Before: {len(rows)} players with is_me=True")
        for r in rows:
            print(f"  id={r.id}  username={r.chesscom_username}")
        # Reset all
        await s.execute(update(Player).where(Player.is_me.is_(True)).values(is_me=False))
        # Set the real me
        result = await s.execute(
            update(Player).where(Player.chesscom_username == me_username).values(is_me=True)
        )
        print(f"\nReset done. Marked '{me_username}' (rows updated: {result.rowcount})")
        await s.commit()
        rows = list((await s.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalars())
        print(f"After:  {len(rows)} players with is_me=True")
        for r in rows:
            print(f"  id={r.id}  username={r.chesscom_username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

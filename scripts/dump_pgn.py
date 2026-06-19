"""Dump the PGN of one of my games to stdout — for piping into debrief.py."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Game

async def main(gid: int) -> int:
    async with SessionLocal() as s:
        g = (await s.execute(select(Game).where(Game.id == gid))).scalar_one_or_none()
        if not g:
            print(f"Game {gid} not found", file=sys.stderr); return 1
        sys.stdout.write(g.pgn or "")
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(int(sys.argv[1]))))

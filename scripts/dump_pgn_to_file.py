"""Dump a game's PGN to a UTF-8 file (PowerShell's `>` would write UTF-16)."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Game

async def main(gid: int, out_path: str) -> int:
    async with SessionLocal() as s:
        g = (await s.execute(select(Game).where(Game.id == gid))).scalar_one_or_none()
        if not g: return 1
        Path(out_path).write_text(g.pgn or "", encoding="utf-8")
        print(f"wrote {len(g.pgn or '')} chars to {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(int(sys.argv[1]), sys.argv[2])))

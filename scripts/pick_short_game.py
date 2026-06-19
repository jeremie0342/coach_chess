"""Find a short game I lost, for testing live debrief."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import or_, select
from app.db.session import SessionLocal
from app.models import Game, Player

async def main() -> int:
    async with SessionLocal() as s:
        me = (await s.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        g = (await s.execute(
            select(Game)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.ply_count > 0, Game.ply_count <= 30)
            .order_by(Game.played_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if not g:
            print("no short game found"); return 1
        print(f"game_id={g.id} plies={g.ply_count} url={g.url}")
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

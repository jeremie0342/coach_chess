"""Find the first game where my rating reached the given threshold."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import case, func, or_, select

from app.db.session import SessionLocal
from app.models import Game, Player


async def main(threshold: int = 400) -> None:
    async with SessionLocal() as s:
        me = (await s.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        # My rating per game (either as white or black)
        my_rating = case(
            (Game.white_player_id == me.id, Game.white_rating),
            else_=Game.black_rating,
        )
        q = (
            select(Game.id, Game.played_at, my_rating.label("my_rating"))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(my_rating >= threshold)
            .order_by(Game.played_at.asc())
            .limit(1)
        )
        first = (await s.execute(q)).first()
        if not first:
            print(f"Never reached {threshold}.")
            return
        print(f"First game at rating >= {threshold}: id={first.id}  played_at={first.played_at}  rating={first.my_rating}")

        # Count games from that point onward
        n = (await s.execute(
            select(func.count(Game.id))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.played_at >= first.played_at)
        )).scalar_one()
        print(f"Games from that point onward: {n}")

        plies = (await s.execute(
            select(func.coalesce(func.sum(Game.ply_count), 0))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.played_at >= first.played_at)
        )).scalar_one()
        print(f"Total plies: {plies}")


if __name__ == "__main__":
    threshold = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    asyncio.run(main(threshold))

"""Quick DB stats check."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import Game, Move, Player


async def main() -> None:
    async with SessionLocal() as s:
        players = (await s.execute(select(func.count(Player.id)))).scalar_one()
        games = (await s.execute(select(func.count(Game.id)))).scalar_one()
        moves = (await s.execute(select(func.count(Move.id)))).scalar_one()
        me_q = await s.execute(select(Player).where(Player.is_me.is_(True)))
        me = me_q.scalars().first()
        print(f"players: {players}")
        print(f"games:   {games}")
        print(f"moves:   {moves}")
        print(f"me:      {me.chesscom_username if me else 'NONE'}")

        # Win/loss/draw breakdown for me
        if me:
            from app.models.game import GameResult
            for result in GameResult:
                white = (await s.execute(
                    select(func.count(Game.id)).where(
                        Game.white_player_id == me.id, Game.result == result
                    )
                )).scalar_one()
                black = (await s.execute(
                    select(func.count(Game.id)).where(
                        Game.black_player_id == me.id, Game.result == result
                    )
                )).scalar_one()
                print(f"  result={result.value}: white={white} black={black}")

            # Top openings
            print("\nTop ECO codes:")
            rows = (await s.execute(
                select(Game.eco, func.count(Game.id).label("n"))
                .where((Game.white_player_id == me.id) | (Game.black_player_id == me.id))
                .group_by(Game.eco)
                .order_by(func.count(Game.id).desc())
                .limit(10)
            )).all()
            for eco, n in rows:
                print(f"  {eco or '(none)'}: {n}")

            # Time class breakdown
            print("\nTime class:")
            rows = (await s.execute(
                select(Game.time_class, func.count(Game.id))
                .group_by(Game.time_class)
            )).all()
            for tc, n in rows:
                print(f"  {tc or '(none)'}: {n}")


if __name__ == "__main__":
    asyncio.run(main())

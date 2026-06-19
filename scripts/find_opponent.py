"""Find a frequent opponent to use as a scout test target."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import case, func, or_, select
from app.db.session import SessionLocal
from app.models import Game, Player


async def main() -> int:
    async with SessionLocal() as s:
        me = (await s.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        opp_id = case(
            (Game.white_player_id == me.id, Game.black_player_id),
            else_=Game.white_player_id,
        )
        q = (
            select(opp_id.label("opp"), func.count(Game.id))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .group_by("opp")
            .order_by(func.count(Game.id).desc())
            .limit(10)
        )
        rows = (await s.execute(q)).all()
        print("Top opponents:")
        for opp_id_v, n in rows:
            p = (await s.execute(select(Player).where(Player.id == opp_id_v))).scalar_one_or_none()
            if p:
                print(f"  {n:>3}× vs {p.chesscom_username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

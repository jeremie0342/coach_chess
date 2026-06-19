"""Print the auto-difficulty's next-ELO recommendation."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Player
from app.services.auto_difficulty import recommend_next_elo


async def main() -> int:
    async with SessionLocal() as s:
        me = (await s.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        r = await recommend_next_elo(s, me)
    print(f"Next ELO         : {r.next_elo}")
    print(f"Last ELO          : {r.last_elo}")
    print(f"Sessions used    : {r.sessions_used}")
    print(f"Recent score     : {r.score}")
    print(f"Win streak       : {r.win_streak}")
    print(f"Loss streak      : {r.loss_streak}")
    print(f"Reason           : {r.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

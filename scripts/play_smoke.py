"""Non-interactive smoke test of the play engine."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Player, PositionSession
from app.services.play_engine import apply_user_move, start_session
from app.services.stockfish import shutdown_engine

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


async def main() -> int:
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
        sess = await start_session(
            session, starting_fen=START, user_color="white",
            skill_level=5, sf_elo=1200, depth=10,
            title="smoke test", source="manual",
            player_id=me.id if me else None,
        )
        print(f"Started session #{sess.id}  status={sess.status}")
        print(f"  current_fen: {sess.current_fen}")

        # Play 1. e4
        r = await apply_user_move(session, sess, "e4")
        print(f"\nUser played e4: accepted={r.accepted}")
        print(f"  SF replied: {r.engine_san} ({r.engine_uci})  eval={r.eval_cp}")
        print(f"  current_fen: {r.new_fen}")

        # Play 2. Nf3
        r = await apply_user_move(session, sess, "Nf3")
        print(f"\nUser played Nf3: accepted={r.accepted}")
        print(f"  SF replied: {r.engine_san}  eval={r.eval_cp}")

    await shutdown_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

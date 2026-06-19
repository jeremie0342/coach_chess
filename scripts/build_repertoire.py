"""CLI: build my empirical repertoire + compute out-of-book per game.

Run after games are imported (and after openings are loaded). Idempotent.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import and_, case, func, or_, select

from app.db.session import SessionLocal
from app.models import Game, Player, RepertoireNode
from app.models.repertoire import RepertoireColor
from app.services.openings.out_of_book import compute_out_of_book_for_all_my_games
from app.services.openings.repertoire_builder import build_repertoire


async def amain() -> int:
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
        if not me:
            print("No 'is_me' player. Import games first.")
            return 1

        print(f"Building empirical repertoire for {me.chesscom_username}...")
        rep_stats = await build_repertoire(session, me)
        print(f"  nodes inserted: {rep_stats['nodes_inserted']}")
        print(f"  positions seen: {rep_stats['positions_seen']}")

        print("\nComputing out-of-book markers for every game...")
        oob = await compute_out_of_book_for_all_my_games(session, me)
        print(f"  games processed: {oob['games_processed']}")

        # Quick aggregates
        avg_my_oob = (await session.execute(
            select(func.avg(Game.my_out_of_book_ply))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.my_out_of_book_ply.is_not(None))
        )).scalar()
        avg_opp_oob = (await session.execute(
            select(func.avg(Game.opp_out_of_book_ply))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.opp_out_of_book_ply.is_not(None))
        )).scalar()
        print(f"\n  Avg ply where I leave book:        {float(avg_my_oob or 0):.1f}")
        print(f"  Avg ply where opponent leaves book: {float(avg_opp_oob or 0):.1f}")

        print(f"\nTop-10 repertoire positions (WHITE):")
        await _print_top_lines(session, me, RepertoireColor.WHITE, n=10)
        print(f"\nTop-10 repertoire positions (BLACK):")
        await _print_top_lines(session, me, RepertoireColor.BLACK, n=10)
    return 0


async def _print_top_lines(session, me: Player, color: RepertoireColor, n: int) -> None:
    rows = list((await session.execute(
        select(RepertoireNode)
        .where(RepertoireNode.color == color)
        .order_by(RepertoireNode.created_at.asc())
        .limit(n)
    )).scalars())
    for r in rows:
        label = (r.label or "").splitlines()[0]
        print(f"  [{r.id:>4}] {label}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))

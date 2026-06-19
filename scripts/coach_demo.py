"""Demo: ask the LLM coach to explain a specific move in one of my games.

Usage:
    uv run python scripts/coach_demo.py --game-id 1 --ply 12
    uv run python scripts/coach_demo.py --game-id 1 --review
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Game, Player
from app.services.coach.explainer import explain_move
from app.services.coach.game_review import review_player_mistakes


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        game = (await session.execute(
            select(Game).where(Game.id == args.game_id)
        )).scalar_one_or_none()
        if not game:
            print(f"Game {args.game_id} not found.")
            return 1
        me = (await session.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalar_one_or_none()

        if args.review:
            items = await review_player_mistakes(session, game, me, max_items=args.max)
            print(f"\n=== Coach review for game #{game.id} ({game.url}) ===\n")
            for it in items:
                print(f"-- Ply {it.ply}  [{it.quality}, cp_loss={it.cp_loss}]")
                print(f"   You played: {it.played}    Best: {it.best}")
                print(f"   Coach:\n   {it.explanation}\n")
        else:
            r = await explain_move(session, game, args.ply, use_cache=not args.no_cache)
            if "error" in r:
                print(r["error"])
                return 1
            print(f"\nGame #{r['game_id']}  ply={r['ply']}  trait aux {r['side_to_move']}")
            print(f"You played: {r['played']}    Best: {r['best']}    "
                  f"Quality: {r['quality']}    cp_loss: {r['cp_loss']}")
            if r.get("opening"):
                print(f"Opening: {r['opening']}")
            print(f"\nCoach:\n{r['explanation']}\n")
            print(f"(cache_hit={r['cache_hit']})")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--game-id", type=int, required=True)
    p.add_argument("--ply", type=int, help="Single ply to explain")
    p.add_argument("--review", action="store_true", help="Full review of player's worst moves")
    p.add_argument("--max", type=int, default=5, help="Max items in review mode")
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args()
    if not args.review and args.ply is None:
        p.error("Pass --ply N or --review")
    raise SystemExit(asyncio.run(amain(args)))

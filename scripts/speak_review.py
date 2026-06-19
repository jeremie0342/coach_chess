"""Read a game review aloud through Windows SAPI.

Usage:
    uv run python scripts/speak_review.py --game-id 1
    uv run python scripts/speak_review.py --game-id 1 --max 3 --rate -1
    uv run python scripts/speak_review.py --text "Bonjour, je suis ton coach"
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
from app.services.coach.game_review import review_player_mistakes
from app.services.tts import speak


async def amain(args: argparse.Namespace) -> int:
    if args.text:
        result = speak(args.text, rate=args.rate, volume=args.volume)
        print(f"spoken={result.spoken}  backend={result.backend}  reason={result.reason}")
        return 0 if result.spoken else 1

    async with SessionLocal() as session:
        game = (await session.execute(select(Game).where(Game.id == args.game_id))).scalar_one_or_none()
        if not game:
            print(f"Game {args.game_id} not found", file=sys.stderr); return 1
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
        items = await review_player_mistakes(session, game, me, max_items=args.max)

    if not items:
        speak(f"La partie {args.game_id} n'a pas d'erreurs majeures détectées.", rate=args.rate)
        return 0

    intro = f"Revoyons les {len(items)} pires moments de la partie {args.game_id}."
    print(f">> {intro}")
    speak(intro, rate=args.rate, volume=args.volume)
    for it in items:
        side = it.side_to_move
        head = f"Coup {it.ply}, tu as joué {it.played}. Le meilleur coup était {it.best}."
        print(f"\n>> Ply {it.ply}: {it.played} (best {it.best}, cp_loss {it.cp_loss})")
        speak(head, rate=args.rate, volume=args.volume)
        if it.explanation:
            print(f"   coach: {it.explanation[:200]}{'...' if len(it.explanation) > 200 else ''}")
            speak(it.explanation, rate=args.rate, volume=args.volume)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--game-id", type=int, help="Game to review aloud")
    p.add_argument("--text", help="Just speak this text and exit")
    p.add_argument("--max", type=int, default=3, help="Max blunders to cover")
    p.add_argument("--rate", type=int, default=0, help="SAPI rate [-10..10]")
    p.add_argument("--volume", type=int, default=90, help="SAPI volume [0..100]")
    args = p.parse_args()
    if not args.game_id and not args.text:
        p.error("Pass --game-id N or --text 'message'")
    raise SystemExit(asyncio.run(amain(args)))

"""Scout a Chess.com opponent and print a battle plan.

Usage:
    uv run python scripts/scout.py hikaru
    uv run python scripts/scout.py someuser --months 6 --max-games 200 --no-llm
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.scout.scout import scout_opponent


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        r = await scout_opponent(
            session,
            opponent_username=args.username,
            max_months=args.months,
            max_games=args.max_games,
            generate_plan=not args.no_llm,
        )

    o = r.opening_report
    print(f"\n=== Scout report: {r.opponent_username} ({r.elapsed_s:.1f}s) ===")
    print(f"Games imported this run: {r.games_imported}  (already in DB: {r.games_skipped})")
    print(f"Total games in DB:       {o.games_seen}")
    if o.avg_out_of_book_ply:
        print(f"Avg out-of-book ply:     {o.avg_out_of_book_ply:.1f}")

    def _moves(title: str, ms):
        if not ms:
            return
        print(f"\n{title}:")
        for m in ms:
            print(f"  {m.san:>6}  n={m.games:>3}  W/L/D={m.wins}/{m.losses}/{m.draws}  wr={m.winrate:.0%}")

    _moves("First move as White", o.first_move_as_white)
    _moves("Response to 1.e4 (Black)", o.response_to_e4)
    _moves("Response to 1.d4 (Black)", o.response_to_d4)
    _moves("Response to 1.Nf3 (Black)", o.response_to_nf3)

    if o.top_openings_white:
        print("\nTop openings (White):")
        for op in o.top_openings_white:
            print(f"  {op.eco or '???'}  {op.name or '-':<45}  n={op.games:>3}  wr={op.winrate:.0%}")
    if o.top_openings_black:
        print("\nTop openings (Black):")
        for op in o.top_openings_black:
            print(f"  {op.eco or '???'}  {op.name or '-':<45}  n={op.games:>3}  wr={op.winrate:.0%}")

    print(f"\nWeaknesses (top {len(r.weaknesses)}):")
    for w in r.weaknesses[:10]:
        phase = f" [{w['phase']}]" if w.get("phase") else ""
        print(f"  - {w['category']}{phase}: sev={w['severity']:.2f}  occ={w['occurrences']}")

    if r.battle_plan:
        print("\n=== Battle plan (coach) ===")
        print(r.battle_plan)

    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("username", help="Opponent's Chess.com username")
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--max-games", type=int, default=100)
    p.add_argument("--no-llm", action="store_true", help="Skip the LLM battle plan")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

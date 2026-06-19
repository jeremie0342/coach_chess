"""Live debrief of a PGN you paste or pass from a file.

Usage:
    uv run python scripts/debrief.py path/to/game.pgn
    uv run python scripts/debrief.py - < game.pgn        # stdin
    uv run python scripts/debrief.py game.pgn --color black --no-llm
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.live_debrief import live_debrief
from app.services.stockfish import shutdown_engine


def _read_pgn(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return Path(arg).read_text(encoding="utf-8")


async def amain(args: argparse.Namespace) -> int:
    pgn = _read_pgn(args.pgn).strip()
    if not pgn:
        print("Empty PGN.", file=sys.stderr)
        return 1

    async with SessionLocal() as session:
        report = await live_debrief(
            session,
            pgn_text=pgn,
            my_color=args.color,
            depth=args.depth,
            max_blunders=args.max_blunders,
            generate_puzzles=not args.no_puzzles,
            explain_with_llm=not args.no_llm,
        )

    print(f"\n=== Debrief — game #{report.game_id} ({report.elapsed_s:.1f}s) ===")
    print(f"Played as:     {report.my_color}")
    print(f"Opening:       {report.opening or '-'} ({report.eco or '-'})")
    print(f"Out of book at ply: {report.my_out_of_book_ply or '-'}")
    print(f"Moves analyzed: {report.moves_analyzed}")
    print()
    print("Per-phase errors:")
    for phase, p in report.phases.items():
        print(f"  {phase:>11}: blunders={p.blunders}  mistakes={p.mistakes}  inacc={p.inaccuracies}")
    print()
    print(f"Top {len(report.top_blunders)} blunders/mistakes:")
    for it in report.top_blunders:
        print(f"\n-- ply {it.ply}  [{it.quality}, cp_loss={it.cp_loss}]")
        print(f"   You played: {it.played_san}    Best: {it.best_san}")
        if it.exercise_id:
            print(f"   -> puzzle generated: exercise #{it.exercise_id}")
        if it.explanation:
            print(f"   Coach:\n   {it.explanation}")

    print(f"\nPuzzles generated this run: {report.exercises_generated}")
    await shutdown_engine()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("pgn", help="Path to .pgn file (or '-' for stdin)")
    p.add_argument("--color", choices=["white", "black"], help="My color (auto-detected if omitted)")
    p.add_argument("--depth", type=int, help="Override Stockfish depth")
    p.add_argument("--max-blunders", type=int, default=5)
    p.add_argument("--no-llm", action="store_true", help="Skip LLM explanations (faster)")
    p.add_argument("--no-puzzles", action="store_true", help="Don't generate exercises")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

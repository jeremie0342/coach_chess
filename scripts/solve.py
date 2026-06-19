"""Interactive solver: drill puzzles built from your own blunders.

Usage:
    uv run python scripts/solve.py
    uv run python scripts/solve.py --kind tactic --max 10
    uv run python scripts/solve.py --theme missed_win
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Exercise
from app.models.exercise import ExerciseKind
from app.services.exercises.solver import compute_stats, grade_answer, pick_next_due


PIECE_UNICODE = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}


def render_board(fen: str, flip: bool = False) -> str:
    board = chess.Board(fen)
    rows = str(board).split("\n")
    if flip:
        rows = list(reversed(rows))
    out = []
    for i, row in enumerate(rows):
        rank = 8 - i if not flip else i + 1
        cells = []
        for ch in row.split():
            cells.append("·" if ch == "." else PIECE_UNICODE.get(ch, ch))
        out.append(f"  {rank}  {' '.join(cells)}")
    files = "a b c d e f g h" if not flip else "h g f e d c b a"
    out.append(f"     {files}")
    out.append(f"  ({'White' if board.turn == chess.WHITE else 'Black'} to play)")
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--kind", choices=["tactic", "endgame", "opening", "positional", "calculation"])
    p.add_argument("--theme", help="Filter by tag (e.g. fork, pin, missed_win, drops_queen)")
    p.add_argument("--source", choices=["blunder", "lichess", "manual"],
                   help="Restrict to puzzles from this source")
    p.add_argument("--rating", type=int, help="Target your ELO (puzzles within +/- window)")
    p.add_argument("--rating-window", type=int, default=150)
    p.add_argument("--max", type=int, default=15)
    return p.parse_args()


async def amain(args: argparse.Namespace) -> int:
    kind = ExerciseKind(args.kind) if args.kind else None

    async with SessionLocal() as session:
        s = await compute_stats(session, kind=kind)
        print(f"\n=== Exercises (your blunders) ===")
        print(f"Total: {s.total}  |  New: {s.new}  |  Learning: {s.learning}  "
              f"|  Due now: {s.due_today}")
        if s.next_due_at:
            print(f"Next review: {s.next_due_at.isoformat()}")
        if s.total == 0:
            print("\nNo exercises yet. Run scripts/generate_exercises.py first.")
            return 0
        print()

        solved = right = wrong = 0
        for i in range(1, args.max + 1):
            nxt = await pick_next_due(
                session, kind=kind, theme=args.theme,
                source_kind=args.source, rating=args.rating,
                rating_window=args.rating_window,
            )
            if not nxt:
                print("\nNo more exercises matching the filter.")
                break
            ex = nxt.exercise
            board = chess.Board(ex.fen)
            flip = (board.turn == chess.BLACK)

            tag = "NEW" if nxt.is_new else "DUE"
            src = str(ex.source_kind) if ex.source_kind else "?"
            print(f"--- Puzzle {i}/{args.max}  [{tag}]  diff={ex.difficulty}  source={src}  ex#{ex.id}")
            if ex.title:
                print(f"   {ex.title}")
            print(render_board(ex.fen, flip=flip))
            print(f"   themes: {', '.join(ex.theme_tags or [])}")
            print()

            t0 = time.perf_counter()
            try:
                user_move = input("Find the best move (SAN or UCI, 'q' to quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye.")
                break
            t_ms = int((time.perf_counter() - t0) * 1000)
            if user_move.lower() in ("q", "quit", "exit"):
                break

            # rebind to fresh session row
            db_ex = (await session.execute(
                select(Exercise).where(Exercise.id == ex.id)
            )).scalar_one()
            r = await grade_answer(session, db_ex, user_move, time_ms=t_ms)

            solved += 1
            if r.correct:
                right += 1
                print(f"  ✅ Correct ({r.expected_san}). Next review in {r.new_interval_days}d.\n")
            else:
                wrong += 1
                print(f"  ❌ Expected: {r.expected_san} (you played: {r.user_uci or '?'}).")
                print(f"  Next review in {r.new_interval_days}d.")
                # If we have a follow-up PV, show one ply for context
                if db_ex.solution_uci and len(db_ex.solution_uci) > 1:
                    try:
                        b2 = chess.Board(db_ex.fen)
                        san_seq = b2.variation_san([chess.Move.from_uci(u) for u in db_ex.solution_uci[:4]])
                        print(f"  Continuation: {san_seq}")
                    except Exception:
                        pass
                print()

        print(f"\nSession done. {right}/{solved} correct.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain(parse_args())))

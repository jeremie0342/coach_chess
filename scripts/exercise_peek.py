"""Peek at the first exercise the solver would pick — non-interactive smoke test."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess

from app.db.session import SessionLocal
from app.services.exercises.solver import compute_stats, pick_next_due


async def amain() -> int:
    async with SessionLocal() as session:
        s = await compute_stats(session)
        print(f"Total: {s.total}  New: {s.new}  Learning: {s.learning}  Due: {s.due_today}")
        nxt = await pick_next_due(session)
        if not nxt:
            print("(no exercise)")
            return 0
        ex = nxt.exercise
        b = chess.Board(ex.fen)
        try:
            best_san = b.san(chess.Move.from_uci(ex.solution_uci[0]))
        except Exception:
            best_san = ex.solution_uci[0]
        print(f"\nPick: ex#{ex.id}  diff={ex.difficulty}  kind={ex.kind}")
        print(f"  title : {ex.title}")
        print(f"  themes: {ex.theme_tags}")
        print(f"  fen   : {ex.fen}")
        print(f"  side  : {ex.side_to_move}")
        print(f"  best  : {best_san} ({ex.solution_uci[0]})")
        print()
        print(b)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))

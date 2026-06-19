"""Interactive trainer CLI.

Usage:
    uv run python scripts/train.py             # mix both colors
    uv run python scripts/train.py --color white
    uv run python scripts/train.py --color black --max 20
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
from app.models import RepertoireNode
from app.models.repertoire import RepertoireColor
from app.services.trainer.session import (
    compute_stats,
    grade_answer,
    pick_next_due,
)


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
            if ch == ".":
                cells.append("·")
            else:
                cells.append(PIECE_UNICODE.get(ch, ch))
        out.append(f"  {rank}  {' '.join(cells)}")
    files = "a b c d e f g h" if not flip else "h g f e d c b a"
    out.append(f"     {files}")
    out.append(f"  ({'White' if board.turn == chess.WHITE else 'Black'} to play)")
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--color", choices=["white", "black"], help="Drill one color only")
    p.add_argument("--max", type=int, default=20, help="Max cards this session")
    return p.parse_args()


async def amain(args: argparse.Namespace) -> int:
    color = RepertoireColor(args.color) if args.color else None

    async with SessionLocal() as session:
        s = await compute_stats(session, color=color)
        print(f"\n=== Repertoire trainer ===")
        print(f"Total cards: {s.total_nodes}  |  New: {s.new_nodes}  "
              f"|  Learning: {s.learning_nodes}  |  Due now: {s.due_today}")
        if s.next_due_at:
            print(f"Next review scheduled: {s.next_due_at.isoformat()}")
        print()

        reviewed = right = wrong = 0
        for i in range(1, args.max + 1):
            card = await pick_next_due(session, color=color)
            if not card:
                print("\nNo more cards available.")
                break
            n = card.node
            board = chess.Board(n.fen)
            flip = (board.turn == chess.BLACK)

            tag = "NEW" if card.is_new else "DUE"
            print(f"--- Card {i}/{args.max}  [{tag}]  color={n.color}  node#{n.id}")
            print(render_board(n.fen, flip=flip))
            print()
            t0 = time.perf_counter()
            try:
                user_move = input("Your move (SAN or UCI, or 'q' to quit, '?' for hint): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye.")
                break
            t_ms = int((time.perf_counter() - t0) * 1000)
            if user_move.lower() in ("q", "quit", "exit"):
                break
            if user_move == "?":
                print(f"  Hint label: {n.label}")
                print(f"  Alternates:\n{n.notes}\n")
                continue

            # Fresh-fetch the node to bind to this session (transaction safety)
            node_q = await session.execute(
                select(RepertoireNode).where(RepertoireNode.id == n.id)
            )
            db_node = node_q.scalar_one()
            result = await grade_answer(session, db_node, user_move, time_ms=t_ms)

            reviewed += 1
            if result.correct:
                right += 1
                print(f"  ✅ Correct ({result.expected_san}). Next review in "
                      f"{result.new_interval_days}d.\n")
            else:
                wrong += 1
                tag = "alternate you've played" if result.grade == 2 else "wrong"
                print(f"  ❌ {tag}. Expected: {result.expected_san} "
                      f"(played: {result.user_uci or '?'}).")
                if result.alternates:
                    print(f"  Your historical moves from this position:")
                    print("  " + result.alternates.replace("\n", "\n  "))
                print(f"  Next review in {result.new_interval_days}d.\n")

        print(f"\nSession done. {right}/{reviewed} correct.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain(parse_args())))

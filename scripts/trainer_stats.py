"""Quick: show trainer stats without entering an interactive session."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.repertoire import RepertoireColor
from app.services.trainer.session import compute_stats, pick_next_due


async def amain() -> int:
    async with SessionLocal() as session:
        print("=== Trainer stats ===")
        for color in (None, RepertoireColor.WHITE, RepertoireColor.BLACK):
            s = await compute_stats(session, color=color)
            label = str(color) if color else "ALL"
            print(f"\n[{label}]")
            print(f"  total cards : {s.total_nodes}")
            print(f"  new         : {s.new_nodes}")
            print(f"  learning    : {s.learning_nodes}")
            print(f"  due now     : {s.due_today}")
            print(f"  next due_at : {s.next_due_at.isoformat() if s.next_due_at else '-'}")

        print("\n=== First card the trainer would pick (white) ===")
        c = await pick_next_due(session, color=RepertoireColor.WHITE)
        if c:
            n = c.node
            print(f"  is_new={c.is_new}  node#{n.id}")
            print(f"  fen   : {n.fen}")
            print(f"  label : {n.label}")

        print("\n=== First card the trainer would pick (black) ===")
        c = await pick_next_due(session, color=RepertoireColor.BLACK)
        if c:
            n = c.node
            print(f"  is_new={c.is_new}  node#{n.id}")
            print(f"  fen   : {n.fen}")
            print(f"  label : {n.label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))

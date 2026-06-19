"""Non-interactive smoke test of the adaptive picker."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chess
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Exercise
from app.services.exercises.solver import pick_next_due


async def main() -> int:
    async with SessionLocal() as s:
        cases = [
            ("default (your blunders, easiest first)", {}),
            ("Lichess only, around ELO 464",            {"source_kind": "lichess", "rating": 464}),
            ("Lichess fork theme around ELO 464",       {"source_kind": "lichess", "theme": "fork", "rating": 464}),
            ("Lichess mateIn1 around ELO 464",          {"source_kind": "lichess", "theme": "mateIn1", "rating": 464}),
            ("Lichess endgame around ELO 464",          {"source_kind": "lichess", "theme": "endgame", "rating": 464}),
            ("Lichess endgame around ELO 1200 (next stop)", {"source_kind": "lichess", "theme": "endgame", "rating": 1200}),
        ]
        for label, kwargs in cases:
            print(f"\n--- {label}")
            nxt = await pick_next_due(s, **kwargs)
            if not nxt:
                print("  (none)")
                continue
            ex = nxt.exercise
            b = chess.Board(ex.fen)
            try:
                best_san = b.san(chess.Move.from_uci(ex.solution_uci[0]))
            except Exception:
                best_san = ex.solution_uci[0]
            print(f"  ex#{ex.id}  src={ex.source_kind}  diff={ex.difficulty}  is_new={nxt.is_new}")
            print(f"  themes  : {(ex.theme_tags or [])[:8]}")
            print(f"  side    : {ex.side_to_move}")
            print(f"  best    : {best_san} ({ex.solution_uci[0]})")
            if ex.lichess_id:
                print(f"  lichess : https://lichess.org/training/{ex.lichess_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

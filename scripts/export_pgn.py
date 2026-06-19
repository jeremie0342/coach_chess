"""Export a game's annotated PGN to file or stdout.

Usage:
    uv run python scripts/export_pgn.py --game-id 349 > game_349.pgn
    uv run python scripts/export_pgn.py --game-id 349 --output data/g349.pgn
    uv run python scripts/export_pgn.py --game-id 349 --llm --warm
    uv run python scripts/export_pgn.py --game-id 349 --no-eval --no-best
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Game
from app.services.pgn_exporter import (
    ExportOptions,
    export_annotated_pgn,
    export_with_fresh_llm,
)


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        game = (await session.execute(select(Game).where(Game.id == args.game_id))).scalar_one_or_none()
        if not game:
            print(f"Game {args.game_id} not found", file=sys.stderr)
            return 1
        opts = ExportOptions(
            include_llm=args.llm,
            llm_only_worst=args.max_llm,
            include_eval=not args.no_eval,
            include_best_move_hint=not args.no_best,
        )
        if args.warm:
            pgn = await export_with_fresh_llm(session, game, max_explanations=args.max_llm)
        else:
            pgn = await export_annotated_pgn(session, game, opts)

    if args.output:
        Path(args.output).write_text(pgn, encoding="utf-8")
        print(f"Wrote {len(pgn)} chars to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(pgn)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--game-id", type=int, required=True)
    p.add_argument("--output", help="Write to file instead of stdout")
    p.add_argument("--llm", action="store_true", help="Inline LLM coach comments")
    p.add_argument("--warm", action="store_true",
                   help="Generate missing LLM comments on the fly (slow)")
    p.add_argument("--max-llm", type=int, default=5)
    p.add_argument("--no-eval", action="store_true")
    p.add_argument("--no-best", action="store_true")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

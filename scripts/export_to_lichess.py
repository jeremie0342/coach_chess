"""Export your games as a multi-chapter PGN bundle for Lichess Study upload.

Two modes:

  1. File output (no auth):
       uv run python scripts/export_to_lichess.py --output data/bundle.pgn
     Then go to https://lichess.org/study, create a study, click
     "Add new chapter" → "Import PGN", paste the file content. Each game
     becomes a chapter.

  2. Direct push (needs LICHESS_TOKEN with study:write scope in .env):
       uv run python scripts/export_to_lichess.py --study-id abcd1234

Filters:
       --eco D00 --color black --only-losses --limit 30 --llm
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Player
from app.services.lichess_studies import build_pgn_bundle, push_to_study


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        me = (await session.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalar_one_or_none()
        if not me:
            print("No is_me player.", file=sys.stderr); return 1

        if args.study_id:
            try:
                s = await push_to_study(
                    session, me, study_id=args.study_id,
                    eco=args.eco, color=args.color,
                    only_losses=args.only_losses,
                    limit=args.limit, include_llm=args.llm,
                )
            except RuntimeError as e:
                print(f"ERROR: {e}", file=sys.stderr); return 1
            print(f"Pushed {s.chapters_pushed} chapters into study {args.study_id} "
                  f"({s.bytes_sent / 1024:.1f} KB sent)")
            if s.chapters_failed:
                print(f"  ! {s.chapters_failed} failed")
                for err in s.errors[:5]:
                    print(f"    - {err}")
            print(f"\nView at https://lichess.org/study/{args.study_id}")
            return 0

        # File mode
        pgn, games = await build_pgn_bundle(
            session, me,
            eco=args.eco, color=args.color,
            only_losses=args.only_losses,
            limit=args.limit, include_llm=args.llm,
        )
        if not args.output:
            sys.stdout.write(pgn)
            return 0
        Path(args.output).write_text(pgn, encoding="utf-8")
        print(
            f"Wrote {len(games)} games ({len(pgn) / 1024:.1f} KB) to {args.output}\n"
            f"Upload at https://lichess.org/study — Add new chapter → Import PGN → paste."
        )
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", help="Write PGN bundle to file (else stdout)")
    p.add_argument("--study-id", help="Push directly to this Lichess study (needs token)")
    p.add_argument("--eco", help="Filter by ECO code")
    p.add_argument("--color", choices=["white", "black"])
    p.add_argument("--only-losses", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--llm", action="store_true", help="Include LLM coach comments inline")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

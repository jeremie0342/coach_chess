"""CLI: import games from Chess.com into Postgres.

Usage:
    uv run python scripts/import_games.py --full
    uv run python scripts/import_games.py --month 2026 06
    uv run python scripts/import_games.py --full --username someoneelse
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.import_orchestrator import import_full_history, import_month


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        if args.full:
            stats = await import_full_history(session, username=args.username)
        else:
            stats = await import_month(session, args.year, args.month, username=args.username)

    print(
        f"imported={stats.imported} updated={stats.updated} "
        f"skipped={stats.skipped} failed={stats.failed}"
    )
    if stats.errors:
        print("First errors:")
        for err in stats.errors[:5]:
            print(f"  - {err}")
    return 0 if stats.failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Import entire history")
    parser.add_argument("--month", nargs=2, type=int, metavar=("YEAR", "MONTH"),
                        help="Import a single month (e.g. --month 2026 06)")
    parser.add_argument("--username", help="Override CHESSCOM_USERNAME from .env")
    args = parser.parse_args()

    if not args.full and not args.month:
        parser.error("Pass either --full or --month YEAR MONTH")

    if args.month:
        args.year, args.month = args.month
    else:
        args.year = None

    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())

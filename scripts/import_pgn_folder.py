"""Bulk-import every PGN game found under a folder.

Supports multi-game PGN files. Idempotent (sha1 of each game's PGN string is
the unique external_id, same as the live debrief flow).

Usage:
    uv run python scripts/import_pgn_folder.py path/to/folder
    uv run python scripts/import_pgn_folder.py path/to/folder --recursive
    uv run python scripts/import_pgn_folder.py path/to/folder --color black
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess
import chess.pgn

from app.db.session import SessionLocal
from app.models import Player
from app.services.live_debrief import _ingest_pgn
from sqlalchemy import select


def _split_pgn_text(text: str) -> list[str]:
    """Split a multi-game PGN blob into individual game strings."""
    games: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("[Event") and current:
            games.append("\n".join(current).strip())
            current = []
        current.append(line)
    if current:
        last = "\n".join(current).strip()
        if last:
            games.append(last)
    return games


async def amain(args: argparse.Namespace) -> int:
    root = Path(args.folder)
    if not root.exists():
        print(f"Folder not found: {root}", file=sys.stderr)
        return 1

    pattern = "**/*.pgn" if args.recursive else "*.pgn"
    files = sorted(root.glob(pattern))
    print(f"Found {len(files)} .pgn files under {root}")

    started = time.perf_counter()
    total_games = imported = skipped = failed = 0

    async with SessionLocal() as session:
        me = (await session.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalar_one_or_none()
        if not me:
            print("No is_me player. Run an import first.", file=sys.stderr)
            return 1

        for fp in files:
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                print(f"  ! cannot read {fp.name}: {e}", file=sys.stderr)
                continue
            games = _split_pgn_text(text)
            for pgn in games:
                total_games += 1
                try:
                    _, status = await _ingest_pgn(
                        session, pgn, me, my_color_hint=args.color,
                    )
                except Exception as e:
                    failed += 1
                    print(f"  ! ingest failed in {fp.name}: {e}", file=sys.stderr)
                    continue
                if status == "new":
                    imported += 1
                elif status == "existing":
                    skipped += 1
            if total_games % 50 == 0:
                await session.commit()
                print(f"  ...{total_games} games processed", flush=True)
        await session.commit()

    print(
        f"\nDone in {time.perf_counter() - started:.1f}s. "
        f"files={len(files)} games={total_games} imported={imported} "
        f"already_in_db={skipped} failed={failed}"
    )
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("folder", help="Directory containing .pgn files")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--color", choices=["white", "black"],
                   help="Force my color if PGN headers don't include the configured Chess.com username")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

"""Download Syzygy 3-4-5 piece tablebases from a public mirror.

Source: https://tablebase.lichess.ovh/tables/standard/

3-piece set : ~150 KB (trivial)
4-piece set : ~50 MB
5-piece set : ~900 MB (~150 files)

Usage:
    uv run python scripts/download_syzygy.py --pieces 3   # tiny smoke test
    uv run python scripts/download_syzygy.py --pieces 4   # ~50 MB
    uv run python scripts/download_syzygy.py --pieces 5   # ~900 MB (long)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.services.tablebase import TB_DIR


BASE_URLS = {
    3: "https://tablebase.lichess.ovh/tables/standard/3-4-5/",
    4: "https://tablebase.lichess.ovh/tables/standard/3-4-5/",
    5: "https://tablebase.lichess.ovh/tables/standard/3-4-5/",
}


# Hand-picked file lists for the 3-piece and 4-piece subsets (these are
# the practical endgames most useful at 450-1500 ELO). For full 5-piece
# coverage we fall back to scanning the index page.
THREE_PIECE = [
    "KPvK.rtbw", "KPvK.rtbz",
    "KQvK.rtbw", "KQvK.rtbz",
    "KRvK.rtbw", "KRvK.rtbz",
    "KBvK.rtbw", "KBvK.rtbz",
    "KNvK.rtbw", "KNvK.rtbz",
]

FOUR_PIECE = [
    "KPPvK.rtbw", "KPPvK.rtbz",
    "KPvKP.rtbw", "KPvKP.rtbz",
    "KQvKP.rtbw", "KQvKP.rtbz",
    "KQvKQ.rtbw", "KQvKQ.rtbz",
    "KQvKR.rtbw", "KQvKR.rtbz",
    "KRPvK.rtbw", "KRPvK.rtbz",
    "KRvKP.rtbw", "KRvKP.rtbz",
    "KRvKR.rtbw", "KRvKR.rtbz",
    "KRvKB.rtbw", "KRvKB.rtbz",
    "KRvKN.rtbw", "KRvKN.rtbz",
    "KBPvK.rtbw", "KBPvK.rtbz",
    "KNPvK.rtbw", "KNPvK.rtbz",
    "KBNvK.rtbw", "KBNvK.rtbz",
    "KBBvK.rtbw", "KBBvK.rtbz",
]


async def _fetch_one(client: httpx.AsyncClient, base: str, name: str) -> int:
    dest = TB_DIR / name
    if dest.exists() and dest.stat().st_size > 0:
        return 0
    url = base + name
    async with client.stream("GET", url) as r:
        if r.status_code != 200:
            print(f"  ! {name}: HTTP {r.status_code}")
            return 0
        size = 0
        with dest.open("wb") as f:
            async for chunk in r.aiter_bytes(chunk_size=64 * 1024):
                f.write(chunk)
                size += len(chunk)
        return size


async def amain(args: argparse.Namespace) -> int:
    TB_DIR.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    if args.pieces >= 3:
        files.extend(THREE_PIECE)
    if args.pieces >= 4:
        files.extend(FOUR_PIECE)

    base = BASE_URLS[args.pieces]
    print(f"Downloading {len(files)} files to {TB_DIR}...")
    started = time.time()
    total_bytes = 0
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(None, connect=30.0), follow_redirects=True,
        headers={"User-Agent": "coach_chess/0.1"},
    ) as client:
        for i, name in enumerate(files, start=1):
            try:
                n = await _fetch_one(client, base, name)
            except Exception as e:
                print(f"  ! {name}: {e}")
                continue
            total_bytes += n
            print(f"  [{i}/{len(files)}] {name}: {n / 1024:.1f} KB", flush=True)
    print(f"\nDone in {time.time() - started:.1f}s. Total downloaded: {total_bytes / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pieces", type=int, choices=[3, 4, 5], default=4,
                   help="Up to which piece count (cumulative)")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

"""Stream-load the full Lichess puzzle database into the `exercises` table.

Source: https://database.lichess.org/lichess_db_puzzle.csv.zst (CC0).

CSV columns:
    PuzzleId, FEN, Moves, Rating, RatingDeviation, Popularity,
    NbPlays, Themes, GameUrl, OpeningTags

We use PostgreSQL's COPY for ingest speed (~50-100k rows/s).

Idempotent on lichess_id: a stable PuzzleId is what Lichess assigns.
We INSERT ... ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import psycopg
import zstandard as zstd

from app.core.config import PROJECT_ROOT, get_settings

LICHESS_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
LOCAL_PATH = PROJECT_ROOT / "data" / "lichess_db_puzzle.csv.zst"

BATCH_SIZE = 10_000


def conn_kwargs() -> dict:
    s = get_settings()
    # Parse sync URL: postgresql+psycopg://user:pass@host:port/db
    from urllib.parse import urlparse
    p = urlparse(s.database_url_sync.replace("postgresql+psycopg://", "postgresql://"))
    kw = {
        "host": p.hostname or "localhost",
        "port": p.port or 5432,
        "user": p.username or "postgres",
        "dbname": (p.path or "/coach_chess").lstrip("/"),
    }
    if p.password:
        kw["password"] = p.password
    return kw


async def download_if_missing(force: bool = False) -> Path:
    if LOCAL_PATH.exists() and not force:
        size_mb = LOCAL_PATH.stat().st_size / 1024 / 1024
        print(f"Using cached file: {LOCAL_PATH} ({size_mb:.1f} MB)")
        return LOCAL_PATH
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {LICHESS_URL}...")
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(None, connect=30.0),
        follow_redirects=True,
        headers={"User-Agent": "coach_chess/0.1"},
    ) as client:
        async with client.stream("GET", LICHESS_URL) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            written = 0
            last_print = time.time()
            with LOCAL_PATH.open("wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    written += len(chunk)
                    if time.time() - last_print > 2:
                        if total:
                            pct = (written / total) * 100
                            print(f"  {written / 1024 / 1024:.1f} / {total / 1024 / 1024:.0f} MB ({pct:.1f}%)", flush=True)
                        else:
                            print(f"  {written / 1024 / 1024:.1f} MB", flush=True)
                        last_print = time.time()
    print(f"Saved to {LOCAL_PATH} ({written / 1024 / 1024:.1f} MB)")
    return LOCAL_PATH


def stream_rows(path: Path):
    """Yield parsed CSV rows from a .zst file."""
    dctx = zstd.ZstdDecompressor()
    with path.open("rb") as f:
        with dctx.stream_reader(f) as decompressed:
            text = io.TextIOWrapper(decompressed, encoding="utf-8", newline="")
            reader = csv.reader(text)
            header = next(reader, None)
            expected = ["PuzzleId", "FEN", "Moves"]
            if not header or header[:3] != expected:
                raise RuntimeError(f"Unexpected CSV header: {header}")
            for row in reader:
                if len(row) < 10:
                    continue
                yield row


def build_record(row: list[str]) -> tuple | None:
    """Convert one CSV row into a tuple matching our INSERT columns."""
    pid, fen, moves, rating, rd, pop, plays, themes, _game_url, opening_tags = row[:10]
    try:
        # Side to move from FEN
        parts = fen.split()
        side = parts[1] if len(parts) > 1 else "w"
        moves_list = moves.split()
        themes_list = themes.split() if themes else []
        opening_list = opening_tags.split() if opening_tags else []
        rating_i = int(rating) if rating else 1500
        rd_i = int(rd) if rd else None
        pop_i = int(pop) if pop else None
        plays_i = int(plays) if plays else None
    except Exception:
        return None

    kind = "endgame" if "endgame" in themes_list else "tactic"
    return (
        None,                # player_id
        "lichess",           # source_kind
        pid,                 # lichess_id
        None,                # source_game_id
        None,                # source_move_id
        None,                # source_weakness_id
        kind,                # kind
        f"Lichess puzzle {pid}",  # title
        fen,                 # fen
        side,                # side_to_move
        moves_list,          # solution_uci
        rating_i,            # difficulty
        rd_i,                # rating_deviation
        pop_i,               # popularity
        plays_i,             # nb_plays
        themes_list,         # theme_tags
        opening_list,        # opening_tags
        None,                # explanation
        2.5,                 # sr_ease
        0,                   # sr_interval_days
        0,                   # sr_repetitions
        None,                # sr_due_at
        None,                # sr_last_reviewed_at
        0,                   # attempts
        0,                   # successes
    )


COPY_COLUMNS = (
    "player_id, source_kind, lichess_id, source_game_id, source_move_id, "
    "source_weakness_id, kind, title, fen, side_to_move, solution_uci, "
    "difficulty, rating_deviation, popularity, nb_plays, theme_tags, "
    "opening_tags, explanation, sr_ease, sr_interval_days, sr_repetitions, "
    "sr_due_at, sr_last_reviewed_at, attempts, successes, created_at, updated_at"
)


def copy_into_staging(conn, batch: list[tuple]) -> None:
    """Bulk-load a batch into a temp staging table, then merge with ON CONFLICT DO NOTHING."""
    import json
    with conn.cursor() as cur:
        # Ensure staging table exists (in-tx temp; recreated per call)
        cur.execute("""
            CREATE TEMP TABLE IF NOT EXISTS exercises_staging (LIKE exercises INCLUDING DEFAULTS)
            ON COMMIT DELETE ROWS;
        """)
        # Use COPY for raw speed
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        with cur.copy(f"COPY exercises_staging ({COPY_COLUMNS}) FROM STDIN") as cp:
            for rec in batch:
                # rec is the 25-tuple from build_record; append created_at, updated_at
                full = list(rec) + [now, now]
                # Serialize JSONB / list / None as Postgres COPY text format
                cells = []
                for v in full:
                    if v is None:
                        cells.append("\\N")
                    elif isinstance(v, list):
                        cells.append(json.dumps(v))
                    elif isinstance(v, bool):
                        cells.append("t" if v else "f")
                    else:
                        s = str(v)
                        s = s.replace("\\", "\\\\").replace("\t", " ").replace("\n", " ").replace("\r", " ")
                        cells.append(s)
                cp.write("\t".join(cells) + "\n")

        cur.execute(f"""
            INSERT INTO exercises ({COPY_COLUMNS})
            SELECT {COPY_COLUMNS} FROM exercises_staging
            ON CONFLICT (lichess_id) DO NOTHING;
        """)


def ingest(path: Path, limit: int | None) -> dict:
    start = time.time()
    seen = inserted = 0
    last_print = time.time()
    with psycopg.connect(**conn_kwargs(), autocommit=False) as conn:
        batch: list[tuple] = []
        for row in stream_rows(path):
            rec = build_record(row)
            if rec is None:
                continue
            batch.append(rec)
            seen += 1
            if limit and seen >= limit:
                break
            if len(batch) >= BATCH_SIZE:
                copy_into_staging(conn, batch)
                conn.commit()
                inserted += len(batch)
                batch.clear()
                if time.time() - last_print > 3:
                    rate = inserted / max(time.time() - start, 0.1)
                    print(f"  inserted {inserted:,} so far ({rate:,.0f}/s)", flush=True)
                    last_print = time.time()
        if batch:
            copy_into_staging(conn, batch)
            conn.commit()
            inserted += len(batch)
    return {
        "seen": seen,
        "inserted": inserted,
        "elapsed_s": time.time() - start,
    }


async def amain(args: argparse.Namespace) -> int:
    path = await download_if_missing(force=args.redownload)
    print(f"\nIngesting puzzles into Postgres (BATCH={BATCH_SIZE:,})...")
    stats = ingest(path, limit=args.limit)
    rate = stats["inserted"] / max(stats["elapsed_s"], 0.1)
    print(f"\nDone in {stats['elapsed_s']:.1f}s")
    print(f"  rows seen     : {stats['seen']:,}")
    print(f"  rows inserted : {stats['inserted']:,} ({rate:,.0f}/s)")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, help="Stop after N rows (for quick tests)")
    p.add_argument("--redownload", action="store_true")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

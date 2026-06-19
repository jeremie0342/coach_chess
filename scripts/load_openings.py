"""Load the Lichess opening theory database.

Source: https://github.com/lichess-org/chess-openings (public domain).

We pull the 5 TSV files (a.tsv .. e.tsv), each row of the form:
    eco<TAB>name<TAB>pgn<TAB>uci<TAB>epd
Older versions may have just (eco, name, pgn). We tolerate both.
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess
import chess.pgn
import httpx
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Opening
from app.services.openings.theory import fen_signature

LICHESS_BASE = "https://raw.githubusercontent.com/lichess-org/chess-openings/master"
FILES = ["a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv"]


async def fetch_tsv(client: httpx.AsyncClient, name: str) -> str:
    print(f"Fetching {name}...", flush=True)
    r = await client.get(f"{LICHESS_BASE}/{name}", timeout=30.0)
    r.raise_for_status()
    return r.text


def _moves_from_pgn(pgn_text: str) -> list[chess.Move]:
    """Parse a Lichess opening PGN snippet like '1. e4 e5 2. Nf3' into moves."""
    game = chess.pgn.read_game(io.StringIO(pgn_text + " *"))
    if not game:
        return []
    moves: list[chess.Move] = []
    node = game
    while node.variations:
        nxt = node.variation(0)
        if nxt.move is None:
            break
        moves.append(nxt.move)
        node = nxt
    return moves


def parse_rows(tsv_text: str) -> list[tuple[str, str, str, str, str]]:
    """Yield (eco, name, pgn_san, uci_str, fen_signature)."""
    rows: list[tuple[str, str, str, str, str]] = []
    for raw_line in tsv_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Skip headers if any
        if line.lower().startswith(("eco\t", "eco ")):
            continue
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        eco = cols[0].strip()
        name = cols[1].strip()
        pgn = cols[2].strip()

        board = chess.Board()
        moves = _moves_from_pgn(pgn)
        if not moves:
            continue
        for m in moves:
            board.push(m)
        uci_str = " ".join(m.uci() for m in moves)
        san_str = pgn
        sig = board.epd()
        rows.append((eco, name, san_str, uci_str, sig))
    return rows


async def amain() -> int:
    headers = {
        "User-Agent": "coach_chess/0.1 (loading public-domain opening DB)",
        "Accept": "text/plain",
    }
    all_rows: list[tuple[str, str, str, str, str]] = []
    async with httpx.AsyncClient(headers=headers) as client:
        for name in FILES:
            try:
                text = await fetch_tsv(client, name)
            except httpx.HTTPError as e:
                print(f"  ! {name} failed: {e}", file=sys.stderr)
                continue
            parsed = parse_rows(text)
            print(f"  {name}: {len(parsed)} rows parsed", flush=True)
            all_rows.extend(parsed)

    if not all_rows:
        print("No opening rows parsed. Aborting.", file=sys.stderr)
        return 1

    print(f"\nUpserting {len(all_rows)} openings into Postgres...")
    inserted = updated = 0
    async with SessionLocal() as session:
        # Pre-fetch existing signatures to do batched upserts cheaply
        existing_q = await session.execute(select(Opening.id, Opening.fen_signature))
        existing_by_sig = {sig: oid for oid, sig in existing_q.all()}

        # Sort by length of moves_uci so deeper variations come last and override
        # shorter ones with same FEN (in case of dup sigs)
        all_rows.sort(key=lambda r: len(r[3]))

        for eco, name, san_str, uci_str, sig in all_rows:
            if sig in existing_by_sig:
                op = await session.get(Opening, existing_by_sig[sig])
                op.eco = eco
                op.name = name
                op.moves_san = san_str
                op.moves_uci = uci_str
                updated += 1
            else:
                op = Opening(
                    eco=eco, name=name,
                    moves_san=san_str, moves_uci=uci_str,
                    fen_signature=sig,
                )
                session.add(op)
                existing_by_sig[sig] = -1  # marker so we don't re-add in same batch
                inserted += 1

        await session.commit()
    print(f"\nDone. inserted={inserted}  updated={updated}  total={inserted + updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))

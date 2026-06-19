"""Generate an animated GIF of a game segment or puzzle solution.

Usage:
    # Plies 20-30 of game #1
    uv run python scripts/make_gif.py --game-id 1 --start-ply 20 --end-ply 30 --output data/seq.gif

    # Whole solution of an exercise
    uv run python scripts/make_gif.py --exercise 8 --output data/ex8.gif

    # Custom: FEN + UCI moves
    uv run python scripts/make_gif.py --fen "..." --moves e2e4,e7e5,g1f3 --output data/custom.gif
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Exercise, Game, Move
from app.services.position_gif import GifOptions, frames_from_moves, render_gif


async def _frames(args: argparse.Namespace):
    if args.exercise:
        async with SessionLocal() as s:
            ex = (await s.execute(select(Exercise).where(Exercise.id == args.exercise))).scalar_one_or_none()
            if not ex:
                return None, f"exercise {args.exercise} not found"
            frames = frames_from_moves(ex.fen, ex.solution_uci or [])
            if frames and ex.title:
                frames[0].caption = ex.title
            return frames, None

    if args.game_id is not None:
        async with SessionLocal() as s:
            moves = list((await s.execute(
                select(Move).where(Move.game_id == args.game_id).order_by(Move.ply)
            )).scalars())
        if not moves:
            return None, f"no moves for game {args.game_id}"
        end = args.end_ply or len(moves)
        sel = [m for m in moves if args.start_ply <= m.ply <= end]
        if not sel:
            return None, "empty ply range"
        captions = [f"{m.move_number}.{'..' if not m.is_white else ''} {m.san}" for m in sel]
        return frames_from_moves(sel[0].fen_before, [m.uci for m in sel], captions), None

    if args.fen and args.moves:
        return frames_from_moves(args.fen, args.moves.split(",")), None

    return None, "need --exercise, --game-id, or --fen+--moves"


async def amain(args: argparse.Namespace) -> int:
    frames, err = await _frames(args)
    if err:
        print(err, file=sys.stderr); return 1
    if not frames:
        print("no frames", file=sys.stderr); return 1
    opts = GifOptions(frame_duration_ms=args.frame_ms, board_size=args.size)
    data = render_gif(frames, opts)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"Wrote {len(data) / 1024:.1f} KB, {len(frames)} frames to {out}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="data/sequence.gif")
    p.add_argument("--exercise", type=int)
    p.add_argument("--game-id", type=int)
    p.add_argument("--start-ply", type=int, default=1)
    p.add_argument("--end-ply", type=int)
    p.add_argument("--fen")
    p.add_argument("--moves", help="comma-separated UCI moves")
    p.add_argument("--frame-ms", type=int, default=900)
    p.add_argument("--size", type=int, default=480, help="board pixels")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

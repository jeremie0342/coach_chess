"""Generate a shareable PNG card for a position.

Usage:
    # From a free-form FEN
    uv run python scripts/make_card.py --fen "..." --best e2e4 --output card.png

    # From one of your exercises (auto-fills FEN + best + themes)
    uv run python scripts/make_card.py --exercise 8 --output card_ex8.png

    # From a specific ply of one of your games
    uv run python scripts/make_card.py --game-id 1 --ply 27 --output blunder.png
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Exercise, Game, Move, MoveAnalysis
from app.services.position_card import CardOptions, render_card


async def _resolve(args: argparse.Namespace) -> CardOptions | None:
    if args.exercise:
        async with SessionLocal() as s:
            ex = (await s.execute(select(Exercise).where(Exercise.id == args.exercise))).scalar_one_or_none()
            if not ex:
                print(f"Exercise {args.exercise} not found", file=sys.stderr); return None
        opts = CardOptions(
            title=f"Puzzle #{ex.id}",
            subtitle=ex.title or f"diff {ex.difficulty}",
            best_move_uci=ex.solution_uci[0] if ex.solution_uci else None,
            side_to_move_label="Trait aux Blancs" if ex.side_to_move == "w" else "Trait aux Noirs",
            themes=ex.theme_tags or [],
        )
        opts._fen = ex.fen  # type: ignore[attr-defined]
        return opts

    if args.game_id and args.ply is not None:
        async with SessionLocal() as s:
            move = (await s.execute(
                select(Move).where(Move.game_id == args.game_id, Move.ply == args.ply)
            )).scalar_one_or_none()
            if not move:
                print(f"Ply {args.ply} not found in game {args.game_id}", file=sys.stderr); return None
            ana = (await s.execute(
                select(MoveAnalysis).where(MoveAnalysis.move_id == move.id)
            )).scalar_one_or_none()
        opts = CardOptions(
            title=f"Game #{args.game_id} — ply {args.ply}",
            subtitle=f"You played {move.san}",
            best_move_uci=ana.best_move_uci if ana else None,
            eval_cp=ana.eval_cp if ana else None,
            eval_mate=ana.eval_mate if ana else None,
            side_to_move_label="Trait aux Blancs" if chess.Board(move.fen_before).turn == chess.WHITE else "Trait aux Noirs",
            themes=ana.tags if ana else None,
        )
        opts._fen = move.fen_before
        return opts

    if args.fen:
        opts = CardOptions(
            title=args.title or "Position",
            best_move_uci=args.best,
            side_to_move_label="Trait aux Blancs" if chess.Board(args.fen).turn == chess.WHITE else "Trait aux Noirs",
        )
        opts._fen = args.fen
        return opts
    return None


async def amain(args: argparse.Namespace) -> int:
    opts = await _resolve(args)
    if not opts:
        print("Need --fen, --exercise, or --game-id + --ply", file=sys.stderr); return 1
    fen = getattr(opts, "_fen")
    png = render_card(fen, opts)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"Wrote {len(png) / 1024:.1f} KB to {out}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="data/card.png")
    p.add_argument("--fen")
    p.add_argument("--best", help="UCI of move to draw an arrow for")
    p.add_argument("--title")
    p.add_argument("--exercise", type=int)
    p.add_argument("--game-id", type=int)
    p.add_argument("--ply", type=int)
    raise SystemExit(asyncio.run(amain(p.parse_args())))

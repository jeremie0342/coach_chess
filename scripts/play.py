"""Play a position out against Stockfish from the terminal.

Usage:
    # Play out the standard opening at SF Elo 1200, you as White
    uv run python scripts/play.py --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" --color white --elo 1200

    # Practice a Lucena-position endgame, you as White at strength 5
    uv run python scripts/play.py --fen "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1" --color white --skill 5

    # Play from a position you blundered — load via exercise_id
    uv run python scripts/play.py --exercise 42 --color black --elo 1500

    # Play 1.d4 as black against SF Elo 1500
    uv run python scripts/play.py --color black --elo 1500
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Exercise, Player, PositionSession, PositionSessionMove
from app.services.play_engine import (
    abandon_session,
    apply_user_move,
    start_session,
)
from app.services.stockfish import shutdown_engine


PIECE_UNICODE = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def render(fen: str, flip: bool = False) -> str:
    board = chess.Board(fen)
    rows = str(board).split("\n")
    if flip:
        rows = list(reversed(rows))
    out = []
    for i, row in enumerate(rows):
        rank = 8 - i if not flip else i + 1
        cells = []
        for ch in row.split():
            cells.append("·" if ch == "." else PIECE_UNICODE.get(ch, ch))
        out.append(f"  {rank}  {' '.join(cells)}")
    files = "a b c d e f g h" if not flip else "h g f e d c b a"
    out.append(f"     {files}")
    return "\n".join(out)


async def _resolve_fen(args: argparse.Namespace) -> tuple[str, str | None, str | None]:
    if args.exercise:
        async with SessionLocal() as s:
            ex = (await s.execute(select(Exercise).where(Exercise.id == args.exercise))).scalar_one_or_none()
            if not ex:
                raise SystemExit(f"Exercise {args.exercise} not found")
            return ex.fen, "exercise", f"ex#{ex.id}: {ex.title or '?'}"
    if args.fen:
        return args.fen, "manual", None
    return START_FEN, "manual", "standard start"


async def amain(args: argparse.Namespace) -> int:
    fen, source, title = await _resolve_fen(args)
    flip = args.color == "black"

    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
        # Auto-difficulty: if no --elo given and we have a player, pick the next one
        if args.elo is None and me is not None:
            from app.services.auto_difficulty import recommend_next_elo
            rec = await recommend_next_elo(session, me)
            args.elo = rec.next_elo
            print(f"\n[auto-difficulty] next_elo={rec.next_elo}  reason={rec.reason}")
        sess = await start_session(
            session, starting_fen=fen, user_color=args.color,
            skill_level=args.skill, sf_elo=args.elo, depth=args.depth,
            title=title, source=source,
            player_id=me.id if me else None,
        )
        print(f"\n=== Session #{sess.id}  you={args.color}  SF skill={args.skill} elo={args.elo or '-'} depth={args.depth} ===")
        if title:
            print(f"Position: {title}")

        while True:
            # Re-read fresh state
            sess_row = (await session.execute(
                select(PositionSession).where(PositionSession.id == sess.id)
            )).scalar_one()
            print()
            print(render(sess_row.current_fen, flip=flip))
            print(f"  FEN: {sess_row.current_fen}")
            if str(sess_row.status) != "PositionSessionStatus.ACTIVE":
                last = list((await session.execute(
                    select(PositionSessionMove)
                    .where(PositionSessionMove.session_id == sess.id)
                    .order_by(PositionSessionMove.ply.desc())
                    .limit(1)
                )).scalars())
                print(f"\nGame over: {sess_row.status} ({sess_row.result_reason})")
                if last:
                    print(f"Final move: {last[0].san}")
                break

            board = chess.Board(sess_row.current_fen)
            if (board.turn == chess.WHITE) != (args.color == "white"):
                # Not user's turn; engine should already have played in start_session, but loop safety
                print("Waiting for engine...")
                from app.services.play_engine import _play_engine_turn
                await _play_engine_turn(session, sess_row)
                await session.commit()
                continue

            try:
                user_move = input("Your move (SAN or UCI, 'q' to abandon): ").strip()
            except (EOFError, KeyboardInterrupt):
                await abandon_session(session, sess_row)
                print("\nAbandoned.")
                break
            if user_move.lower() in ("q", "quit", "exit", "abandon"):
                await abandon_session(session, sess_row)
                print("Abandoned.")
                break

            t0 = time.perf_counter()
            r = await apply_user_move(session, sess_row, user_move)
            dt = time.perf_counter() - t0
            if not r.accepted:
                print(f"  ! {r.error}")
                continue
            if r.engine_san:
                ev = ""
                if r.eval_cp is not None:
                    ev = f"  eval={r.eval_cp / 100:+.2f}"
                elif r.eval_mate is not None:
                    ev = f"  eval=M{r.eval_mate:+d}"
                print(f"  You: {r.user_san}    SF: {r.engine_san}{ev}  ({dt:.1f}s)")

    await shutdown_engine()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fen", help="Starting position FEN")
    p.add_argument("--exercise", type=int, help="Load FEN from exercise id")
    p.add_argument("--color", choices=["white", "black"], required=True)
    p.add_argument("--skill", type=int, default=10, help="Stockfish Skill Level 0..20")
    p.add_argument("--elo", type=int, help="Cap engine to UCI_Elo (1320..3190)")
    p.add_argument("--depth", type=int, default=12)
    raise SystemExit(asyncio.run(amain(p.parse_args())))

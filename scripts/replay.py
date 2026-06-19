"""Interactive replay of one of your games — board + eval bar + revealable hints.

Usage:
    uv run python scripts/replay.py --game-id 349
    uv run python scripts/replay.py --game-id 349 --color black

Hotkeys (single char + Enter):
    n   next ply
    p   previous ply
    e   reveal eval at current ply
    b   reveal Stockfish best move
    c   reveal LLM coach comment (uses cache only)
    j N jump to ply N
    g   show game header summary
    q   quit
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
from app.models import Game, Move, MoveAnalysis, Opening, Player
from app.services.coach.explainer import _cache_path as _coach_cache_path
import json


PIECE_UNICODE = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}


def render_board(fen: str, flip: bool = False) -> str:
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
    out.append(f"  ({'White' if board.turn == chess.WHITE else 'Black'} to play)")
    return "\n".join(out)


def eval_bar(eval_cp: int | None, eval_mate: int | None, width: int = 30) -> str:
    """Render a horizontal eval bar from white's POV. Returns a string of width chars."""
    if eval_mate is not None:
        return ("◀" * width if eval_mate < 0 else "▶" * width) + f"  M{abs(eval_mate)}"
    if eval_cp is None:
        return "?" * 5
    # eval_cp from side-to-move's POV — we don't know who; treat as side-POV always
    # For visual, clamp to [-500, 500]
    v = max(-500, min(500, eval_cp))
    pct = (v + 500) / 1000.0
    pos = int(round(pct * width))
    bar = "█" * pos + "░" * (width - pos)
    return f"{bar}  {v / 100:+.2f}"


async def _load_game(session, game_id: int) -> tuple[Game, list[Move], dict[int, MoveAnalysis], str | None]:
    g = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not g:
        raise SystemExit(f"Game {game_id} not found")
    moves = list((await session.execute(
        select(Move).where(Move.game_id == game_id).order_by(Move.ply)
    )).scalars())
    analyses = {
        a.move_id: a for a in (await session.execute(
            select(MoveAnalysis).where(MoveAnalysis.move_id.in_([m.id for m in moves]))
        )).scalars()
    }
    op_name = None
    if g.deepest_opening_id:
        op = (await session.execute(
            select(Opening).where(Opening.id == g.deepest_opening_id)
        )).scalar_one_or_none()
        if op:
            op_name = f"{op.eco} {op.name}"
    return g, moves, analyses, op_name


def _coach_comment(fen_before: str, played_uci: str, best_uci: str | None) -> str | None:
    path = _coach_cache_path(fen_before, played_uci, best_uci)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("explanation") or "").strip() or None
    except Exception:
        return None


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        game, moves, analyses, op_name = await _load_game(session, args.game_id)
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()

    is_white = me and game.white_player_id == me.id
    flip = (args.color == "black") if args.color else (not is_white)

    header_lines = [
        f"=== Replay  game #{game.id} ===",
        f"  White: {game.white_player_id}    Black: {game.black_player_id}",
        f"  Result: {game.result.value if hasattr(game.result, 'value') else game.result}",
        f"  Opening: {op_name or game.opening_name or '-'}",
        f"  Total plies: {len(moves)}",
    ]

    idx = 0   # 0 = before move 1; 1 = after move 1; ... len(moves) = after final move

    while True:
        print("\n" + "\n".join(header_lines))
        if idx == 0:
            fen = moves[0].fen_before if moves else chess.STARTING_FEN
            last_move = None
            ana = None
        else:
            m = moves[idx - 1]
            fen = m.fen_after
            last_move = m
            ana = analyses.get(m.id)

        print()
        print(render_board(fen, flip=flip))
        print(f"\n  Ply {idx} / {len(moves)}")
        if last_move:
            who = "White" if last_move.is_white else "Black"
            print(f"  Last: {who} played {last_move.san}  ({last_move.uci})")

        try:
            cmd = input("\n  [n]ext [p]rev [e]val [b]est [c]oach [j]ump [g]ame [q]uit > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd in ("q", "quit", "exit"):
            break
        if cmd == "n":
            idx = min(len(moves), idx + 1)
        elif cmd == "p":
            idx = max(0, idx - 1)
        elif cmd == "e":
            if ana:
                print(f"\n  Eval after move : {eval_bar(ana.eval_cp, ana.eval_mate)}")
                print(f"  cp_loss         : {ana.cp_loss}")
                print(f"  quality         : {ana.quality}")
                if ana.tags:
                    print(f"  tags            : {', '.join(ana.tags)}")
            else:
                print("\n  (no analysis for this ply)")
            input("  press Enter to continue ")
        elif cmd == "b":
            if ana and ana.best_move_san:
                print(f"\n  Best move was   : {ana.best_move_san}")
                if ana.deep_best_san:
                    print(f"  Deep depth best : {ana.deep_best_san}  (depth {ana.deep_depth})")
            else:
                print("\n  (no best-move data)")
            input("  press Enter to continue ")
        elif cmd == "c":
            if ana and last_move:
                comment = _coach_comment(last_move.fen_before, last_move.uci, ana.best_move_uci)
                if comment:
                    print(f"\n  Coach: {comment}\n")
                else:
                    print("\n  (no cached coach comment — run scripts/coach_demo.py --game-id N --ply M)")
            input("  press Enter to continue ")
        elif cmd == "g":
            print("\n  Moves:")
            for m in moves[:30]:
                marker = ""
                a = analyses.get(m.id)
                if a and a.quality and a.quality.value in ("blunder", "mistake"):
                    marker = "  ??" if a.quality.value == "blunder" else "  ?"
                print(f"    {m.ply:>3}.{'.' if not m.is_white else ''} {m.san}{marker}")
            if len(moves) > 30:
                print(f"    ... ({len(moves) - 30} more)")
            input("  press Enter to continue ")
        elif cmd.startswith("j"):
            try:
                n = int(cmd.split()[1] if " " in cmd else input("  jump to ply: ").strip())
                idx = max(0, min(len(moves), n))
            except (ValueError, IndexError):
                pass
        else:
            print("  (unknown command)")

    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--game-id", type=int, required=True)
    p.add_argument("--color", choices=["white", "black"], help="Force board orientation")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

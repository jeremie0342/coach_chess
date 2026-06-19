"""Stream positions from a connected DGT board (or a mock).

Usage:
    # Real hardware (auto-detect USB)
    uv run python scripts/read_dgt.py

    # Explicit COM port
    uv run python scripts/read_dgt.py --port COM5

    # Mock mode (no hardware needed)
    uv run python scripts/read_dgt.py --mock

    # One-shot read + exit
    uv run python scripts/read_dgt.py --once

    # Stream until you press Ctrl+C, print FEN whenever the board changes
    uv run python scripts/read_dgt.py --interval 0.5
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess

from app.services.dgt_board import DgtBoard, MockDgtBoard, find_dgt_port


PIECE_UNICODE = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}


def _render(fen: str) -> str:
    board = chess.Board(fen)
    rows = str(board).split("\n")
    out = []
    for i, row in enumerate(rows):
        rank = 8 - i
        cells = [("·" if c == "." else PIECE_UNICODE.get(c, c)) for c in row.split()]
        out.append(f"  {rank}  {' '.join(cells)}")
    out.append("     a b c d e f g h")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", help="Serial port (e.g. COM5). Auto-detect if omitted.")
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--mock", action="store_true", help="Use the mock board (no hardware)")
    p.add_argument("--once", action="store_true", help="Print one position and exit")
    p.add_argument("--interval", type=float, default=0.5, help="Poll interval in seconds")
    p.add_argument("--no-board", action="store_true", help="FEN only, no ASCII board")
    args = p.parse_args()

    if args.mock:
        board_iface = MockDgtBoard([
            chess.STARTING_FEN,
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        ])
    else:
        if not args.port:
            port = find_dgt_port()
            if not port:
                print("No DGT board detected on USB. Use --port COMx or --mock.", file=sys.stderr)
                return 1
            print(f"Detected DGT board on {port}", file=sys.stderr)
        board_iface = DgtBoard(port=args.port, baudrate=args.baud)

    try:
        board_iface.connect()
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        return 1

    last_fen = None
    try:
        while True:
            snap = board_iface.read_position()
            placement = snap.fen.split()[0]
            if placement != last_fen:
                print(f"\nFEN: {snap.fen}")
                if not args.no_board:
                    print(_render(snap.fen))
                last_fen = placement
            if args.once:
                break
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                break
    except KeyboardInterrupt:
        pass
    finally:
        board_iface.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

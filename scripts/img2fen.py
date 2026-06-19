"""Convert a board screenshot to a FEN string.

Usage:
    uv run python scripts/img2fen.py path/to/board.png
    uv run python scripts/img2fen.py board.png --side b --flip
    uv run python scripts/img2fen.py board.png --verbose
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.board_ocr import fen_summary, image_to_fen


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("image", help="PNG/JPG of a board (cropped to the 8x8 grid)")
    p.add_argument("--side", choices=["w", "b"], default="w")
    p.add_argument("--flip", action="store_true", help="Board displayed from black's POV")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if not Path(args.image).exists():
        print(f"File not found: {args.image}", file=sys.stderr)
        return 1

    result = image_to_fen(args.image, side_to_move=args.side, flip=args.flip)
    summary = fen_summary(result)
    print(summary["fen"])
    if args.verbose:
        print(f"\nMean confidence : {summary['mean_confidence']}")
        print(f"Min confidence  : {summary['min_confidence']}")
        if summary["low_confidence_cells"]:
            print(f"Low-confidence cells:")
            for c in summary["low_confidence_cells"]:
                print(f"  {c['square']:>3}  guess={c['guess']!r:<4} conf={c['conf']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

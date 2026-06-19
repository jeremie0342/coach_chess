"""Smoke-test the OCR by rendering a card with our own renderer, then decoding."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess
from PIL import Image
from app.services.position_card import CardOptions, render_card
from app.services.board_ocr import image_to_fen, fen_summary


CASES = [
    ("starting position", chess.STARTING_FEN, "w"),
    ("after 1.e4", "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", "b"),
    ("Italian", "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", "b"),
    ("KR vs K endgame", "4k3/8/8/8/8/8/4K3/4R3 w - - 0 1", "w"),
]


def main() -> int:
    n_ok = 0
    for name, fen, side in CASES:
        # Render card just board portion
        opts = CardOptions(board_size=800, sidebar_width=0)
        png = render_card(fen, opts)
        # Crop to board only (sidebar width = 0 already)
        img = Image.open(__import__("io").BytesIO(png)).convert("RGB")
        # We rendered with no sidebar — image is already the board
        result = image_to_fen(img, side_to_move=side, flip=False)
        decoded = result.fen.split()[0]
        expected = fen.split()[0]
        match = decoded == expected
        if match:
            n_ok += 1
        s = fen_summary(result)
        marker = "✓" if match else "✗"
        print(f"{marker} {name:<25}  mean_conf={s['mean_confidence']:.3f}  match={match}")
        if not match:
            print(f"   expected: {expected}")
            print(f"   got     : {decoded}")
    print(f"\n{n_ok}/{len(CASES)} round-trips passed")
    return 0 if n_ok == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())

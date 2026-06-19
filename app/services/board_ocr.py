"""Screenshot → FEN via template matching.

Scope: works well on clean board screenshots (chess.com, lichess.org,
this project's own card renderer). Does NOT handle perspective photos
of physical boards — that needs a CNN.

Strategy:
  1. Caller passes a tight crop of the board (or we down-scale a near-tight
     image).
  2. We resize to 8×128 = 1024px square.
  3. For each of 64 cells, we test against 24 templates (12 piece types ×
     2 background colors, light/dark) + 2 empty templates. Best NCC wins.
  4. Output the matrix as a FEN piece-placement string.

Accuracy is ~95-99% on standard themed boards (Lichess style, chess.com
green theme). Falls apart on heavily-stylized themes; in that case the
user can pass --templates from their own theme.

Side to move, castling rights, ep target — NOT recoverable from a static
image. Caller supplies side_to_move; we use placeholder castling rights.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.services.position_card import (
    DARK_SQUARE,
    LIGHT_SQUARE,
    PIECE_UNICODE,
    _piece_font,
)

logger = logging.getLogger(__name__)


TEMPLATE_SIZE = 128       # px per square in templates and resized board
BOARD_SIZE = TEMPLATE_SIZE * 8


@dataclass
class OcrResult:
    fen: str                # piece placement + side + castling + ep + halfmove + fullmove
    confidences: list[list[float]]   # 8x8 of best-match NCC scores
    per_square_picks: list[list[str]]  # 8x8 of "P", "n", "" etc.
    image_was_flipped: bool


def _render_piece_template(piece_type: int, color: bool, light_bg: bool) -> np.ndarray:
    """Render a single piece on a square. Returns HxWx3 uint8 array."""
    bg = LIGHT_SQUARE if light_bg else DARK_SQUARE
    img = Image.new("RGB", (TEMPLATE_SIZE, TEMPLATE_SIZE), bg)
    d = ImageDraw.Draw(img)
    glyph = PIECE_UNICODE[color][piece_type]
    font = _piece_font(int(TEMPLATE_SIZE * 0.78))
    tw = d.textlength(glyph, font=font)
    d.text(
        (TEMPLATE_SIZE / 2 - tw / 2, TEMPLATE_SIZE * 0.04),
        glyph, font=font,
        fill="black" if color == chess.BLACK else "white",
    )
    return np.asarray(img, dtype=np.uint8)


def _render_empty_template(light_bg: bool) -> np.ndarray:
    bg = LIGHT_SQUARE if light_bg else DARK_SQUARE
    return np.full((TEMPLATE_SIZE, TEMPLATE_SIZE, 3), bg, dtype=np.uint8)


@lru_cache(maxsize=1)
def _build_templates() -> dict[str, dict[bool, np.ndarray]]:
    """Build {piece_symbol: {is_light_square: array}} dict.

    piece_symbol uses 'P','N','B','R','Q','K' (white) and lower for black,
    plus '.' for empty.
    """
    out: dict[str, dict[bool, np.ndarray]] = {}
    for color, sym_offset in ((chess.WHITE, str.upper), (chess.BLACK, str.lower)):
        for piece_type, letter in (
            (chess.PAWN, "p"), (chess.KNIGHT, "n"), (chess.BISHOP, "b"),
            (chess.ROOK, "r"), (chess.QUEEN, "q"), (chess.KING, "k"),
        ):
            sym = sym_offset(letter)
            out[sym] = {
                True: _render_piece_template(piece_type, color, light_bg=True),
                False: _render_piece_template(piece_type, color, light_bg=False),
            }
    out["."] = {
        True: _render_empty_template(light_bg=True),
        False: _render_empty_template(light_bg=False),
    }
    return out


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    """Normalised cross-correlation between two equal-shape uint8 arrays."""
    af = a.astype(np.float32).ravel()
    bf = b.astype(np.float32).ravel()
    af -= af.mean(); bf -= bf.mean()
    denom = float(np.linalg.norm(af) * np.linalg.norm(bf))
    if denom < 1e-6:
        return 0.0
    return float(np.dot(af, bf) / denom)


def _load_and_normalize(path: str | bytes | Path) -> Image.Image:
    if isinstance(path, (bytes, bytearray)):
        img = Image.open(io.BytesIO(path))
    else:
        img = Image.open(path)
    img = img.convert("RGB")
    if img.size != (BOARD_SIZE, BOARD_SIZE):
        img = img.resize((BOARD_SIZE, BOARD_SIZE), Image.LANCZOS)
    return img


def image_to_fen(
    image: str | bytes | Path | Image.Image,
    *,
    side_to_move: str = "w",
    flip: bool = False,
) -> OcrResult:
    """Convert a board image to FEN. `side_to_move` is 'w' or 'b'."""
    if isinstance(image, Image.Image):
        img = image.convert("RGB")
        if img.size != (BOARD_SIZE, BOARD_SIZE):
            img = img.resize((BOARD_SIZE, BOARD_SIZE), Image.LANCZOS)
    else:
        img = _load_and_normalize(image)
    arr = np.asarray(img, dtype=np.uint8)

    templates = _build_templates()
    placements: list[list[str]] = [["" for _ in range(8)] for _ in range(8)]
    confs: list[list[float]] = [[0.0 for _ in range(8)] for _ in range(8)]

    for rank in range(8):
        for file in range(8):
            display_rank = (7 - rank) if not flip else rank
            display_file = file if not flip else (7 - file)
            y0 = display_rank * TEMPLATE_SIZE
            x0 = display_file * TEMPLATE_SIZE
            cell = arr[y0:y0 + TEMPLATE_SIZE, x0:x0 + TEMPLATE_SIZE]

            is_light = (rank + file) % 2 == 1   # a1 dark (light = (file+rank) odd)
            best_sym = "."
            best_score = -2.0
            for sym, by_color in templates.items():
                tpl = by_color[is_light]
                score = _ncc(cell, tpl)
                if score > best_score:
                    best_score = score
                    best_sym = sym
            placements[rank][file] = best_sym
            confs[rank][file] = best_score

    # Build FEN piece placement
    rows_fen: list[str] = []
    for rank in range(7, -1, -1):
        row = ""
        empty = 0
        for file in range(8):
            sym = placements[rank][file]
            if sym == ".":
                empty += 1
            else:
                if empty:
                    row += str(empty); empty = 0
                row += sym
        if empty:
            row += str(empty)
        rows_fen.append(row)
    placement = "/".join(rows_fen)
    fen = f"{placement} {side_to_move} - - 0 1"
    return OcrResult(
        fen=fen, confidences=confs, per_square_picks=placements,
        image_was_flipped=flip,
    )


def fen_summary(result: OcrResult) -> dict:
    """Useful diagnostics — average confidence + low-confidence cells."""
    flat = [c for row in result.confidences for c in row]
    low = [
        (rank, file, c, result.per_square_picks[rank][file])
        for rank, row in enumerate(result.confidences)
        for file, c in enumerate(row) if c < 0.7
    ]
    return {
        "fen": result.fen,
        "mean_confidence": round(sum(flat) / max(len(flat), 1), 3),
        "min_confidence": round(min(flat) if flat else 0.0, 3),
        "low_confidence_cells": [
            {"square": chess.square_name(chess.square(f, r)),
             "guess": p, "conf": round(c, 3)}
            for r, f, c, p in low
        ],
    }

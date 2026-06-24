"""Render a chess board to a PIL Image via SVG + svglib.

Replaces the previous Pillow-only `_draw_board` that used Unicode glyphs.
Uses python-chess `chess.svg.board()` (Cburnett piece set, Wikipedia
standard) then rasterizes through svglib + reportlab.

Drop-in replacement: `render_board(board, size, ...) -> PIL.Image`.
"""
from __future__ import annotations

import io
import logging

import chess
import chess.svg
from PIL import Image
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg

logger = logging.getLogger(__name__)


# Warm wooden tones, more pleasing than the default green/cream.
LIGHT_FILL = "#f0d9b5"   # warm cream
DARK_FILL = "#b58863"    # warm wood brown
COORD_COLOR = "#444444"
LASTMOVE_FILL = "#cdd26a"


def render_board(
    board: chess.Board,
    size: int,
    *,
    flip: bool = False,
    arrow_uci: str | None = None,
    highlight_squares: list[int] | None = None,
    coordinates: bool = True,
) -> Image.Image:
    """Render the board as a PIL RGBA image at exactly `size` x `size` pixels."""
    arrows: list[chess.svg.Arrow] = []
    if arrow_uci:
        try:
            mv = chess.Move.from_uci(arrow_uci)
            if mv in board.legal_moves or board.is_legal(mv):
                arrows.append(chess.svg.Arrow(mv.from_square, mv.to_square, color="#5fb35fdc"))
            else:
                arrows.append(chess.svg.Arrow(mv.from_square, mv.to_square, color="#5fb35fdc"))
        except (ValueError, chess.InvalidMoveError):
            pass

    fill = {sq: LASTMOVE_FILL + "80" for sq in (highlight_squares or [])}

    svg_str = chess.svg.board(
        board=board,
        size=size,
        flipped=flip,
        coordinates=coordinates,
        arrows=arrows,
        squares=chess.SquareSet(highlight_squares) if highlight_squares else None,
        fill=fill,
        colors={
            "square light": LIGHT_FILL,
            "square dark": DARK_FILL,
            "square light lastmove": LASTMOVE_FILL,
            "square dark lastmove": "#aaa23a",
            "coord": COORD_COLOR,
        },
    )

    drawing = svg2rlg(io.StringIO(svg_str))
    # svglib computes the drawing in the SVG's native viewport units.
    # We need to scale so the output matches `size`.
    if drawing.width and abs(drawing.width - size) > 0.5:
        scale = size / drawing.width
        drawing.width *= scale
        drawing.height *= scale
        drawing.scale(scale, scale)

    png_bytes = renderPM.drawToString(drawing, fmt="PNG")
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return img

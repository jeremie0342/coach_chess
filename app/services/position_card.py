"""Render a chess position as a shareable PNG card — pure Pillow, no SVG step.

We draw the 8x8 board ourselves, place pieces via Unicode glyphs from
Segoe UI Symbol (Windows) / DejaVu (fallback), and draw an arrow with
basic geometry. Sidebar holds title / eval / best move / themes.

No native dependencies. Output is a single PNG ~30-80 KB depending on
board size.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from math import atan2, cos, sin

import chess
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


PIECE_UNICODE = {
    chess.WHITE: {
        chess.KING: "♔", chess.QUEEN: "♕", chess.ROOK: "♖",
        chess.BISHOP: "♗", chess.KNIGHT: "♘", chess.PAWN: "♙",
    },
    chess.BLACK: {
        chess.KING: "♚", chess.QUEEN: "♛", chess.ROOK: "♜",
        chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟",
    },
}

LIGHT_SQUARE = (238, 238, 210)
DARK_SQUARE = (118, 150, 86)
ARROW_COLOR = (95, 179, 95, 220)


@dataclass
class CardOptions:
    title: str = "Coach chess"
    subtitle: str | None = None
    best_move_uci: str | None = None
    eval_cp: int | None = None
    eval_mate: int | None = None
    side_to_move_label: str | None = None
    themes: list[str] | None = None
    footer: str | None = "coach_chess"
    board_size: int = 600
    sidebar_width: int = 360
    bg_color: tuple[int, int, int] = (49, 46, 43)
    text_color: tuple[int, int, int] = (240, 240, 235)
    accent_color: tuple[int, int, int] = (118, 150, 86)
    flip: bool = False


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _piece_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/seguisym.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_board(d: ImageDraw.ImageDraw, board: chess.Board, ox: int, oy: int, size: int, flip: bool) -> None:
    sq = size // 8
    piece_font = _piece_font(int(sq * 0.78))
    for rank in range(8):
        for file in range(8):
            is_light = (rank + file) % 2 == 1
            color = LIGHT_SQUARE if is_light else DARK_SQUARE
            x = ox + (file if not flip else 7 - file) * sq
            y = oy + (7 - rank if not flip else rank) * sq
            d.rectangle([x, y, x + sq, y + sq], fill=color)
            piece = board.piece_at(chess.square(file, rank))
            if piece:
                glyph = PIECE_UNICODE[piece.color][piece.piece_type]
                tw = d.textlength(glyph, font=piece_font)
                d.text(
                    (x + (sq - tw) / 2, y + sq * 0.04),
                    glyph, font=piece_font,
                    fill="black" if piece.color == chess.BLACK else "white",
                )
    coord_font = _font(int(sq * 0.22))
    for i in range(8):
        file_letter = chr(ord("a") + (i if not flip else 7 - i))
        x = ox + i * sq + sq * 0.04
        d.text((x, oy + size - sq * 0.30), file_letter, font=coord_font, fill=(80, 80, 80))
        rank_label = str(8 - i if not flip else i + 1)
        d.text((ox + sq * 0.04, oy + i * sq + sq * 0.04), rank_label, font=coord_font, fill=(80, 80, 80))


def _square_center(file: int, rank: int, ox: int, oy: int, sq: int, flip: bool) -> tuple[float, float]:
    fx = file if not flip else 7 - file
    fy = 7 - rank if not flip else rank
    return (ox + fx * sq + sq / 2, oy + fy * sq + sq / 2)


def _draw_arrow(card: Image.Image, from_sq: int, to_sq: int, ox: int, oy: int, size: int, flip: bool) -> None:
    sq = size // 8
    fx, fy = chess.square_file(from_sq), chess.square_rank(from_sq)
    tx, ty = chess.square_file(to_sq), chess.square_rank(to_sq)
    x1, y1 = _square_center(fx, fy, ox, oy, sq, flip)
    x2, y2 = _square_center(tx, ty, ox, oy, sq, flip)

    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    width = max(8, sq // 7)
    od.line([(x1, y1), (x2, y2)], fill=ARROW_COLOR, width=width)

    angle = atan2(y2 - y1, x2 - x1)
    head_len = sq * 0.45
    head_half = sq * 0.18
    bx, by = x2, y2
    p1 = (bx - head_len * cos(angle) + head_half * sin(angle),
          by - head_len * sin(angle) - head_half * cos(angle))
    p2 = (bx - head_len * cos(angle) - head_half * sin(angle),
          by - head_len * sin(angle) + head_half * cos(angle))
    od.polygon([(bx, by), p1, p2], fill=ARROW_COLOR)
    card.alpha_composite(overlay)


def _format_eval(eval_cp: int | None, eval_mate: int | None) -> str:
    if eval_mate is not None:
        return f"#{eval_mate}"
    if eval_cp is None:
        return "—"
    if abs(eval_cp) >= 30000:
        return "+∞" if eval_cp > 0 else "-∞"
    return f"{eval_cp / 100:+.2f}"


def _wrap(text: str, width_chars: int) -> list[str]:
    out: list[str] = []
    cur = ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width_chars:
            if cur:
                out.append(cur)
            cur = word
        else:
            cur = (cur + " " + word) if cur else word
    if cur:
        out.append(cur)
    return out


def render_card(fen: str, opts: CardOptions) -> bytes:
    board = chess.Board(fen)
    total_w = opts.board_size + opts.sidebar_width
    total_h = opts.board_size

    card = Image.new("RGBA", (total_w, total_h), opts.bg_color + (255,))
    d = ImageDraw.Draw(card)
    _draw_board(d, board, 0, 0, opts.board_size, opts.flip)

    if opts.best_move_uci:
        try:
            m = chess.Move.from_uci(opts.best_move_uci)
            if m in board.legal_moves:
                _draw_arrow(card, m.from_square, m.to_square, 0, 0, opts.board_size, opts.flip)
        except (ValueError, chess.InvalidMoveError):
            pass

    x = opts.board_size + 24
    y = 30
    d.text((x, y), opts.title, font=_font(32, bold=True), fill=opts.text_color)
    y += 46
    if opts.subtitle:
        d.text((x, y), opts.subtitle, font=_font(19), fill=(210, 210, 205))
        y += 30

    y += 18
    d.text((x, y), _format_eval(opts.eval_cp, opts.eval_mate),
           font=_font(48, bold=True), fill=opts.accent_color)
    y += 64

    if opts.side_to_move_label:
        d.text((x, y), opts.side_to_move_label, font=_font(20), fill=opts.text_color)
        y += 30
    if opts.best_move_uci:
        san = opts.best_move_uci
        try:
            san = board.san(chess.Move.from_uci(opts.best_move_uci))
        except Exception:
            pass
        d.text((x, y), f"Best: {san}", font=_font(20), fill=opts.text_color)
        y += 30
    if opts.themes:
        y += 6
        for line in _wrap(", ".join(opts.themes), 28):
            d.text((x, y), line, font=_font(17), fill=(180, 180, 175))
            y += 22

    if opts.footer:
        d.text((x, total_h - 30), opts.footer, font=_font(16), fill=(150, 150, 145))

    out = io.BytesIO()
    card.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()

"""Render a sequence of board positions as an animated GIF.

We reuse the static board renderer from position_card and stitch
frames into a multi-frame GIF via Pillow. Each frame can show the
move just played as a highlight arrow.

Use cases (covered by helpers below):
  - Animate a ply range of an analyzed game (`gif_from_game`)
  - Animate the solution to a puzzle (`gif_from_exercise`)
  - Animate any list of FENs with optional per-frame arrow / caption
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Iterable

import chess
from PIL import Image, ImageDraw

from app.services.position_card import (
    DARK_SQUARE,
    LIGHT_SQUARE,
    PIECE_UNICODE,
    _draw_board,
    _font,
    _piece_font,
)

logger = logging.getLogger(__name__)

ARROW_COLOR = (95, 179, 95, 220)
HIGHLIGHT_FROM = (255, 235, 110, 100)   # light yellow for from-square
HIGHLIGHT_TO   = (200, 220, 90, 130)    # green-yellow for to-square


@dataclass
class GifFrame:
    fen: str
    arrow_uci: str | None = None     # move to highlight (UCI like e2e4)
    caption: str | None = None


@dataclass
class GifOptions:
    board_size: int = 480
    frame_duration_ms: int = 900
    loop: bool = True
    bg_color: tuple[int, int, int] = (49, 46, 43)
    caption_height: int = 40
    show_coords: bool = True


def _highlight_squares(img: Image.Image, from_sq: int, to_sq: int, board_size: int, flip: bool) -> None:
    sq = board_size // 8
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for square, color in ((from_sq, HIGHLIGHT_FROM), (to_sq, HIGHLIGHT_TO)):
        f, r = chess.square_file(square), chess.square_rank(square)
        x = (f if not flip else 7 - f) * sq
        y = (7 - r if not flip else r) * sq
        od.rectangle([x, y, x + sq, y + sq], fill=color)
    img.alpha_composite(overlay)


def _draw_arrow(img: Image.Image, from_sq: int, to_sq: int, board_size: int, flip: bool) -> None:
    from math import atan2, cos, sin
    sq = board_size // 8
    def _center(s: int) -> tuple[float, float]:
        f, r = chess.square_file(s), chess.square_rank(s)
        fx = f if not flip else 7 - f
        fy = 7 - r if not flip else r
        return (fx * sq + sq / 2, fy * sq + sq / 2)
    x1, y1 = _center(from_sq)
    x2, y2 = _center(to_sq)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    width = max(6, sq // 7)
    od.line([(x1, y1), (x2, y2)], fill=ARROW_COLOR, width=width)
    angle = atan2(y2 - y1, x2 - x1)
    head_len, head_half = sq * 0.45, sq * 0.18
    p1 = (x2 - head_len * cos(angle) + head_half * sin(angle),
          y2 - head_len * sin(angle) - head_half * cos(angle))
    p2 = (x2 - head_len * cos(angle) - head_half * sin(angle),
          y2 - head_len * sin(angle) + head_half * cos(angle))
    od.polygon([(x2, y2), p1, p2], fill=ARROW_COLOR)
    img.alpha_composite(overlay)


def _render_frame(frame: GifFrame, opts: GifOptions, flip: bool) -> Image.Image:
    board = chess.Board(frame.fen)
    canvas_h = opts.board_size + (opts.caption_height if frame.caption else 0)
    img = Image.new("RGBA", (opts.board_size, canvas_h), opts.bg_color + (255,))

    highlights: list[int] = []
    if frame.arrow_uci:
        try:
            mv = chess.Move.from_uci(frame.arrow_uci)
            highlights = [mv.from_square, mv.to_square]
        except (ValueError, chess.InvalidMoveError):
            pass

    _draw_board(
        img, board, 0, 0, opts.board_size, flip,
        arrow_uci=frame.arrow_uci, highlight_squares=highlights or None,
    )

    if frame.caption:
        d = ImageDraw.Draw(img)
        font = _font(20, bold=True)
        d.text(
            (12, opts.board_size + 8),
            frame.caption,
            font=font, fill=(240, 240, 235),
        )
    return img


def render_gif(frames: Iterable[GifFrame], opts: GifOptions | None = None, *, flip: bool = False) -> bytes:
    """Build an animated GIF from frames."""
    opts = opts or GifOptions()
    pil_frames: list[Image.Image] = []
    for f in frames:
        pil_frames.append(_render_frame(f, opts, flip=flip).convert("P", palette=Image.Palette.ADAPTIVE))
    if not pil_frames:
        raise ValueError("no frames")
    out = io.BytesIO()
    pil_frames[0].save(
        out, format="GIF",
        save_all=True,
        append_images=pil_frames[1:],
        duration=opts.frame_duration_ms,
        loop=0 if opts.loop else 1,
        disposal=2,
        optimize=True,
    )
    return out.getvalue()


def render_mp4(frames: Iterable[GifFrame], opts: GifOptions | None = None, *, flip: bool = False) -> bytes:
    """Build an MP4 video from frames using imageio + ffmpeg.

    MP4 is preferable to GIF for sharing on most platforms: pausable,
    scrubbable, consistent frame rate, and 3-5x smaller. Encoded H.264
    (libx264) yuv420p so all browsers and players accept it.

    The imageio ffmpeg backend cannot write to a BytesIO buffer — it needs
    a real file path — so we route through a temp file and read it back.
    """
    import os
    import tempfile
    import imageio.v2 as imageio
    import numpy as np

    opts = opts or GifOptions()
    pil_frames: list[Image.Image] = []
    for f in frames:
        pil_frames.append(_render_frame(f, opts, flip=flip).convert("RGB"))
    if not pil_frames:
        raise ValueError("no frames")

    # H.264 requires constant resolution + even dimensions. Some frames have
    # captions (extra strip below the board) and others don't — normalize all
    # to the max size and pad with background.
    max_w = max(im.width for im in pil_frames)
    max_h = max(im.height for im in pil_frames)
    target_w = max_w + (max_w % 2)
    target_h = max_h + (max_h % 2)
    bg = opts.bg_color
    if any((im.width, im.height) != (target_w, target_h) for im in pil_frames):
        normalized: list[Image.Image] = []
        for im in pil_frames:
            canvas = Image.new("RGB", (target_w, target_h), bg)
            canvas.paste(im, (0, 0))
            normalized.append(canvas)
        pil_frames = normalized

    fps = max(1.0, 1000.0 / opts.frame_duration_ms)

    fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="coach_chess_")
    os.close(fd)
    try:
        # Quality knobs:
        #  - crf 17  : visually lossless (lower = better; 0 = lossless, 51 = worst)
        #  - preset slow : let x264 use more CPU for better compression at same CRF
        #  - tune stillimage : optimized for slow-moving content with text/pieces
        #  - bf 0    : disable B-frames; cleaner stop-frame scrubbing in players
        writer = imageio.get_writer(
            tmp_path, format="ffmpeg", fps=fps, codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=1,
            quality=None,
            output_params=[
                "-crf", "17",
                "-preset", "slow",
                "-tune", "stillimage",
                "-bf", "0",
                "-x264-params", "keyint=15:min-keyint=2",
            ],
        )
        try:
            for im in pil_frames:
                writer.append_data(np.asarray(im))
        finally:
            writer.close()
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---- High-level helpers ----

def frames_from_moves(initial_fen: str, moves_uci: list[str], captions: list[str | None] | None = None) -> list[GifFrame]:
    """Build frames by applying each move from the initial FEN."""
    board = chess.Board(initial_fen)
    frames: list[GifFrame] = [GifFrame(fen=board.fen())]
    for i, uci in enumerate(moves_uci):
        try:
            mv = chess.Move.from_uci(uci)
        except (ValueError, chess.InvalidMoveError):
            continue
        if mv not in board.legal_moves:
            continue
        # Mark the move on the previous frame (so it shows the move about to be played)
        frames[-1].arrow_uci = uci
        if captions and i < len(captions):
            frames[-1].caption = captions[i]
        board.push(mv)
        frames.append(GifFrame(fen=board.fen()))
    return frames

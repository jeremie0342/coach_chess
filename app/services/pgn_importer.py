"""Import a Chess.com game dict into Postgres.

Idempotent: re-importing the same game (by external_id == game URL) updates
in-place rather than duplicating.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, Player
from app.models.game import GameResult, TimeControlCategory


CLOCK_RE = re.compile(r"\[%clk\s+(\d+):(\d+):([\d.]+)\]")


@dataclass
class ImportStats:
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


async def _get_or_create_player(
    session: AsyncSession, username: str, is_me: bool = False
) -> Player:
    username = (username or "?").lower()
    result = await session.execute(
        select(Player).where(Player.chesscom_username == username)
    )
    player = result.scalar_one_or_none()
    if player:
        if is_me and not player.is_me:
            player.is_me = True
        return player
    player = Player(chesscom_username=username, display_name=username, is_me=is_me)
    session.add(player)
    await session.flush()
    return player


def _parse_clock(comment: str) -> float | None:
    if not comment:
        return None
    m = CLOCK_RE.search(comment)
    if not m:
        return None
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def _parse_result(s: str | None) -> GameResult:
    if s == "1-0":
        return GameResult.WHITE_WIN
    if s == "0-1":
        return GameResult.BLACK_WIN
    if s in ("1/2-1/2", "½-½"):
        return GameResult.DRAW
    return GameResult.UNKNOWN


def _normalize_time_class(tc: str | None) -> TimeControlCategory | None:
    if not tc:
        return None
    try:
        return TimeControlCategory(tc.lower())
    except ValueError:
        return None


def _parse_end_time(game: dict[str, Any]) -> datetime | None:
    end = game.get("end_time")
    if end is None:
        return None
    try:
        return datetime.fromtimestamp(int(end), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


async def import_chesscom_game(
    session: AsyncSession,
    game_data: dict[str, Any],
    me_username: str,
) -> tuple[Game | None, str]:
    """Import one Chess.com game dict.

    Returns (game, action) where action ∈ {"imported", "updated", "skipped", "failed"}.
    """
    url = game_data.get("url") or game_data.get("uuid")
    if not url:
        return None, "skipped"

    # Idempotency: check existing
    existing = await session.execute(select(Game).where(Game.external_id == url))
    existing_game = existing.scalar_one_or_none()
    if existing_game is not None:
        return existing_game, "skipped"

    pgn_text = game_data.get("pgn")
    if not pgn_text:
        return None, "skipped"

    try:
        pgn_game = chess.pgn.read_game(io.StringIO(pgn_text))
    except Exception:
        return None, "failed"
    if pgn_game is None:
        return None, "failed"

    headers = pgn_game.headers
    white_info = game_data.get("white", {})
    black_info = game_data.get("black", {})
    white_username = white_info.get("username") or headers.get("White") or "?"
    black_username = black_info.get("username") or headers.get("Black") or "?"

    white_player = await _get_or_create_player(
        session, white_username, is_me=white_username.lower() == me_username.lower()
    )
    black_player = await _get_or_create_player(
        session, black_username, is_me=black_username.lower() == me_username.lower()
    )

    board = pgn_game.board()
    initial_fen = board.fen() if pgn_game.headers.get("SetUp") == "1" else None

    game_row = Game(
        external_id=url,
        source="chess.com",
        url=url,
        white_player_id=white_player.id,
        black_player_id=black_player.id,
        white_rating=white_info.get("rating") or _safe_int(headers.get("WhiteElo")),
        black_rating=black_info.get("rating") or _safe_int(headers.get("BlackElo")),
        result=_parse_result(headers.get("Result")),
        termination=headers.get("Termination"),
        time_control=headers.get("TimeControl") or game_data.get("time_control"),
        time_class=_normalize_time_class(game_data.get("time_class")),
        rated=bool(game_data.get("rated", True)),
        eco=headers.get("ECO"),
        opening_name=headers.get("ECOUrl", "").split("/")[-1].replace("-", " ") or None,
        pgn=pgn_text,
        initial_fen=initial_fen,
        played_at=_parse_end_time(game_data),
        raw=game_data,
        analysis_status="pending",
    )
    session.add(game_row)
    await session.flush()

    # Walk moves
    ply = 0
    node = pgn_game
    while node.variations:
        next_node = node.variation(0)
        move = next_node.move
        if move is None:
            break
        fen_before = board.fen()
        san = board.san(move)
        move_number = board.fullmove_number
        is_white = board.turn == chess.WHITE
        board.push(move)
        fen_after = board.fen()
        ply += 1

        clock = _parse_clock(next_node.comment or "")

        session.add(
            Move(
                game_id=game_row.id,
                ply=ply,
                move_number=move_number,
                is_white=is_white,
                san=san,
                uci=move.uci(),
                fen_before=fen_before,
                fen_after=fen_after,
                clock_seconds=clock,
            )
        )
        node = next_node

    game_row.ply_count = ply
    await session.flush()
    return game_row, "imported"


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

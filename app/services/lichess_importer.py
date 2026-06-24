"""Import Lichess games into Postgres.

Mirrors `pgn_importer.import_chesscom_game` but :
  - identifies "me" via `Player.lichess_username`
  - synthesizes a unique `chesscom_username` for Lichess-only opponents using
    the `lichess:` prefix so the DB unique constraint stays happy
  - tags Game.source = "lichess.org" and external_id = "lichess:{game_id}"
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Game, Move, Player
from app.models.game import GameResult, TimeControlCategory
from app.services.lichess_client import LichessClient
from app.services.pgn_importer import ImportStats, _parse_clock, _parse_result, _safe_int

logger = logging.getLogger(__name__)


async def _get_or_create_lichess_player(
    session: AsyncSession, lichess_username: str, *, is_me: bool = False,
) -> Player:
    """Resolve a Player by lichess_username.

    Order of resolution:
      1. is_me=True : find the unique Player(is_me=True). If its
         lichess_username is empty, fill it in. Don't create a new row.
      2. else : look up by lichess_username. Create if missing, using a
         synthetic chesscom_username (`lichess:{name}`) so the unique
         constraint on chesscom_username holds.
    """
    lichess_username = lichess_username.lower()

    if is_me:
        me = (await session.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalar_one_or_none()
        if me is None:
            # First-time setup: create the owner Player.
            settings = get_settings()
            me = Player(
                chesscom_username=(settings.chesscom_username or lichess_username).lower(),
                lichess_username=lichess_username,
                display_name=settings.coach_display_name or lichess_username,
                is_me=True,
            )
            session.add(me)
            await session.flush()
            return me
        if not me.lichess_username:
            me.lichess_username = lichess_username
        return me

    # Opponent
    existing = (await session.execute(
        select(Player).where(Player.lichess_username == lichess_username)
    )).scalar_one_or_none()
    if existing:
        return existing

    # Synthesize a non-colliding chesscom_username for this Lichess-only opp.
    synthetic = f"lichess:{lichess_username}"
    # Make sure it doesn't collide either (very unlikely but defensive).
    n = 0
    while (await session.execute(
        select(Player).where(Player.chesscom_username == synthetic)
    )).scalar_one_or_none() is not None:
        n += 1
        synthetic = f"lichess:{lichess_username}#{n}"

    p = Player(
        chesscom_username=synthetic,
        lichess_username=lichess_username,
        display_name=lichess_username,
        is_me=False,
    )
    session.add(p)
    await session.flush()
    return p


def _normalize_speed(speed: str | None) -> TimeControlCategory | None:
    if not speed:
        return None
    mapping = {
        "bullet": TimeControlCategory.BULLET,
        "blitz": TimeControlCategory.BLITZ,
        "rapid": TimeControlCategory.RAPID,
        "classical": TimeControlCategory.CLASSICAL,
        "correspondence": TimeControlCategory.DAILY,
    }
    return mapping.get(speed.lower())


def _parse_lichess_end_time(game_data: dict) -> datetime | None:
    end = game_data.get("lastMoveAt") or game_data.get("createdAt")
    if end is None:
        return None
    try:
        # Lichess timestamps are ms since epoch.
        return datetime.fromtimestamp(int(end) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


async def import_lichess_game(
    session: AsyncSession,
    game_data: dict[str, Any],
    me_username: str,
) -> tuple[Game | None, str]:
    """Import one Lichess game JSON dict.

    Returns (game, action) where action ∈ {"imported", "skipped", "failed"}.
    """
    game_id = game_data.get("id")
    if not game_id:
        return None, "skipped"

    external_id = f"lichess:{game_id}"
    existing = (await session.execute(
        select(Game).where(Game.external_id == external_id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing, "skipped"

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
    players_data = game_data.get("players", {})
    white_info = players_data.get("white", {})
    black_info = players_data.get("black", {})
    # Lichess can have anonymous players (no user field)
    white_user = (white_info.get("user") or {}).get("name") or headers.get("White") or "?"
    black_user = (black_info.get("user") or {}).get("name") or headers.get("Black") or "?"

    me_lichess = me_username.lower()
    white_player = await _get_or_create_lichess_player(
        session, white_user, is_me=white_user.lower() == me_lichess,
    )
    black_player = await _get_or_create_lichess_player(
        session, black_user, is_me=black_user.lower() == me_lichess,
    )

    board = pgn_game.board()
    initial_fen = board.fen() if headers.get("SetUp") == "1" else None

    eco = headers.get("ECO") or (game_data.get("opening") or {}).get("eco")
    opening_name = (game_data.get("opening") or {}).get("name") or headers.get("Opening")

    game_row = Game(
        external_id=external_id,
        source="lichess.org",
        url=f"https://lichess.org/{game_id}",
        white_player_id=white_player.id,
        black_player_id=black_player.id,
        white_rating=white_info.get("rating") or _safe_int(headers.get("WhiteElo")),
        black_rating=black_info.get("rating") or _safe_int(headers.get("BlackElo")),
        result=_parse_result(headers.get("Result")),
        termination=headers.get("Termination") or game_data.get("status"),
        time_control=headers.get("TimeControl"),
        time_class=_normalize_speed(game_data.get("speed") or game_data.get("perf")),
        rated=bool(game_data.get("rated", True)),
        eco=eco,
        opening_name=opening_name,
        pgn=pgn_text,
        initial_fen=initial_fen,
        played_at=_parse_lichess_end_time(game_data),
        raw=game_data,
        analysis_status="pending",
    )
    session.add(game_row)
    await session.flush()

    # Walk moves (same shape as the chess.com path)
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
        session.add(Move(
            game_id=game_row.id, ply=ply, move_number=move_number, is_white=is_white,
            san=san, uci=move.uci(),
            fen_before=fen_before, fen_after=fen_after,
            clock_seconds=clock,
        ))
        node = next_node

    game_row.ply_count = ply
    await session.flush()
    return game_row, "imported"


async def import_lichess_user(
    session: AsyncSession,
    lichess_username: str,
    *,
    max_games: int = 100,
    is_me: bool = False,
) -> ImportStats:
    """Pull the most recent `max_games` Lichess games of `username` into DB.

    Idempotent — re-runs skip games already present.
    """
    stats = ImportStats()
    settings = get_settings()
    me_username = (settings.lichess_username or lichess_username).lower() if is_me else "__never_match__"

    async with LichessClient(username=lichess_username) as client:
        async for game in client.stream_games(max_games=max_games):
            try:
                _, action = await import_lichess_game(session, game, me_username)
                if action == "imported":
                    stats.imported += 1
                elif action == "skipped":
                    stats.skipped += 1
                else:
                    stats.failed += 1
            except Exception as e:
                stats.failed += 1
                stats.errors.append(f"{game.get('id', '?')}: {e}")
                logger.warning("Lichess import failed for %s: %s", game.get("id"), e)

    await session.commit()
    logger.info(
        "import_lichess_user %s: imported=%d skipped=%d failed=%d",
        lichess_username, stats.imported, stats.skipped, stats.failed,
    )
    return stats

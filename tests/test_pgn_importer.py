"""PGN importer: idempotency + correct mapping of headers and moves."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import Game, Move, Player
from app.services.pgn_importer import import_chesscom_game


pytestmark = pytest.mark.db


_PGN_SAMPLE = """[Event "Live Chess"]
[Site "https://www.chess.com/game/live/12345"]
[Date "2026.06.01"]
[White "alice"]
[Black "bob"]
[Result "1-0"]
[WhiteElo "500"]
[BlackElo "450"]
[ECO "C50"]
[TimeControl "900+10"]
[Termination "alice won by checkmate"]

1. e4 e5 2. Bc4 Bc5 3. Qh5 Nc6 4. Qxf7# 1-0
"""


def _game_dict(external_id: str = "https://www.chess.com/game/live/12345") -> dict:
    return {
        "url": external_id,
        "pgn": _PGN_SAMPLE,
        "white": {"username": "alice", "rating": 500},
        "black": {"username": "bob", "rating": 450},
        "time_class": "rapid",
        "rated": True,
        "end_time": 1717200000,
    }


async def test_imports_game_and_moves(db_session) -> None:
    game, action = await import_chesscom_game(db_session, _game_dict(), me_username="alice")
    assert action == "imported"
    assert game is not None
    assert game.white_rating == 500
    assert game.black_rating == 450
    assert game.eco == "C50"

    n_moves = (await db_session.execute(
        select(func.count(Move.id)).where(Move.game_id == game.id)
    )).scalar_one()
    assert n_moves == 7    # 4.Qxf7# is ply 7


async def test_re_importing_same_game_is_noop(db_session) -> None:
    g1, action1 = await import_chesscom_game(db_session, _game_dict(), me_username="alice")
    assert action1 == "imported"
    g2, action2 = await import_chesscom_game(db_session, _game_dict(), me_username="alice")
    assert action2 == "skipped"
    assert g2.id == g1.id
    # Only one Game row exists with that external_id
    n = (await db_session.execute(
        select(func.count(Game.id)).where(Game.external_id == "https://www.chess.com/game/live/12345")
    )).scalar_one()
    assert n == 1


async def test_is_me_flag_only_for_provided_username(db_session) -> None:
    await import_chesscom_game(db_session, _game_dict(), me_username="alice")
    me_count = (await db_session.execute(
        select(func.count(Player.id)).where(Player.is_me.is_(True))
    )).scalar_one()
    assert me_count == 1
    me = (await db_session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one()
    assert me.chesscom_username == "alice"


async def test_scout_import_does_not_promote_opponent_to_is_me(db_session) -> None:
    """When importing games from opponent's archive (me_username=alice), if alice
    isn't a player in the PGN, no player should be flagged is_me."""
    await import_chesscom_game(db_session, _game_dict(), me_username="carol")
    me_count = (await db_session.execute(
        select(func.count(Player.id)).where(Player.is_me.is_(True))
    )).scalar_one()
    assert me_count == 0

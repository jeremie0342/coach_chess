"""Detect when a game leaves known opening theory.

For each game we compute two markers:
    my_out_of_book_ply  : earliest ply where MY move was not in the openings DB
    opp_out_of_book_ply : earliest ply where the opponent's move was not in the DB

We also compute the deepest opening position both sides stayed in (used as
the canonical opening label of the game).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, Opening, Player
from app.services.openings.theory import fen_signature

logger = logging.getLogger(__name__)


async def compute_out_of_book_for_game(
    session: AsyncSession, game: Game, me_player_id: int | None = None
) -> dict:
    """Update the game in place with out-of-book markers + deepest opening."""
    moves = list((await session.execute(
        select(Move).where(Move.game_id == game.id).order_by(Move.ply)
    )).scalars())
    if not moves:
        return {"game_id": game.id, "skipped": "no moves"}

    # Bulk fetch all opening signatures touched by this game in ONE query
    all_sigs = {fen_signature(m.fen_after) for m in moves}
    all_sigs.add(fen_signature(moves[0].fen_before))  # starting position
    rows = list((await session.execute(
        select(Opening).where(Opening.fen_signature.in_(all_sigs))
    )).scalars())
    sig_to_op: dict[str, Opening] = {r.fen_signature: r for r in rows}

    my_is_white: bool | None
    if me_player_id is None:
        my_is_white = None
    else:
        my_is_white = game.white_player_id == me_player_id

    my_out: int | None = None
    opp_out: int | None = None
    deepest: Opening | None = None
    deepest_ply: int = 0

    for m in moves:
        sig_after = fen_signature(m.fen_after)
        in_book = sig_after in sig_to_op
        if in_book:
            deepest = sig_to_op[sig_after]
            deepest_ply = m.ply
        if my_is_white is not None:
            is_my_move = (m.is_white == my_is_white)
            if not in_book:
                if is_my_move and my_out is None:
                    my_out = m.ply
                if (not is_my_move) and opp_out is None:
                    opp_out = m.ply

    game.my_out_of_book_ply = my_out
    game.opp_out_of_book_ply = opp_out
    if deepest is not None:
        game.deepest_opening_id = deepest.id
    return {
        "game_id": game.id,
        "my_out_of_book_ply": my_out,
        "opp_out_of_book_ply": opp_out,
        "deepest_opening": deepest.name if deepest else None,
        "deepest_eco": deepest.eco if deepest else None,
        "deepest_ply": deepest_ply,
    }


async def compute_out_of_book_for_all_my_games(
    session: AsyncSession, player: Player
) -> dict:
    games = list((await session.execute(
        select(Game).where(
            (Game.white_player_id == player.id) | (Game.black_player_id == player.id)
        )
    )).scalars())

    processed = 0
    for g in games:
        await compute_out_of_book_for_game(session, g, me_player_id=player.id)
        processed += 1
        # Periodic commits to keep the transaction small
        if processed % 50 == 0:
            await session.commit()
    await session.commit()
    logger.info("Out-of-book computed for %d games of %s", processed, player.chesscom_username)
    return {"games_processed": processed}

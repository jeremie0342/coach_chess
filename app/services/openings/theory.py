"""Match positions against the loaded opening theory."""
from __future__ import annotations

from dataclasses import dataclass

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Opening


@dataclass
class OpeningMatch:
    opening_id: int
    eco: str
    name: str
    moves_san: str


def fen_signature(fen: str) -> str:
    """Compact position fingerprint: piece placement + turn + castling + en passant.

    Same as `chess.Board(fen).epd()` but cheaper if we just need the prefix.
    Lichess opening DB and our theory matching use this exact form.
    """
    board = chess.Board(fen)
    return board.epd()


async def match_position(session: AsyncSession, fen: str) -> OpeningMatch | None:
    sig = fen_signature(fen)
    op = (await session.execute(
        select(Opening).where(Opening.fen_signature == sig)
    )).scalar_one_or_none()
    if not op:
        return None
    return OpeningMatch(
        opening_id=op.id,
        eco=op.eco,
        name=op.name,
        moves_san=op.moves_san,
    )


async def deepest_match_in_game(
    session: AsyncSession, fens_in_order: list[str]
) -> OpeningMatch | None:
    """Return the LAST opening match found along a sequence of positions.

    Used to identify "this game went into the X Variation, specifically".
    """
    if not fens_in_order:
        return None
    # Bulk fetch all matching signatures in one query
    sigs = [fen_signature(f) for f in fens_in_order]
    rows = list((await session.execute(
        select(Opening).where(Opening.fen_signature.in_(sigs))
    )).scalars())
    if not rows:
        return None
    sig_to_op = {r.fen_signature: r for r in rows}
    last: Opening | None = None
    for sig in sigs:
        if sig in sig_to_op:
            last = sig_to_op[sig]
    if not last:
        return None
    return OpeningMatch(
        opening_id=last.id,
        eco=last.eco,
        name=last.name,
        moves_san=last.moves_san,
    )

"""Find positions in the user's past games that are structurally similar to
a target FEN.

Similarity metric (cheap, deterministic):

  signature(fen) = (pawn_bitboard_white, pawn_bitboard_black, material_white, material_black, side_to_move)

We hash the signature for exact matches (same pawn skeleton + material).
For "structurally similar" we also accept positions where the pawn
signatures differ by ≤ K pawn squares — Hamming distance on the pawn
bitboards.

This is good enough at the personal-coach level — way better than nothing,
and computable from existing Move rows (no extra storage). For semantic
position embeddings we'd need a neural net; out of scope.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import chess
from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, MoveAnalysis, Player

logger = logging.getLogger(__name__)


@dataclass
class PositionMatch:
    game_id: int
    ply: int
    fen: str
    distance: int
    quality: str | None
    cp_loss: int | None


def _pawn_bitboards(board: chess.Board) -> tuple[int, int]:
    """Return (white_pawn_bb, black_pawn_bb)."""
    return (
        int(board.pawns & board.occupied_co[chess.WHITE]),
        int(board.pawns & board.occupied_co[chess.BLACK]),
    )


def _material_signature(board: chess.Board) -> tuple[tuple[int, int, int, int, int], tuple[int, int, int, int, int]]:
    """(N, B, R, Q, +pawns) counts per color (we exclude king, always 1)."""
    counts: dict[bool, list[int]] = {chess.WHITE: [0, 0, 0, 0, 0], chess.BLACK: [0, 0, 0, 0, 0]}
    for _, p in board.piece_map().items():
        if p.piece_type == chess.KING:
            continue
        idx = {chess.PAWN: 4, chess.KNIGHT: 0, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 3}[p.piece_type]
        counts[p.color][idx] += 1
    w = tuple(counts[chess.WHITE])
    b = tuple(counts[chess.BLACK])
    return w, b   # type: ignore[return-value]


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


async def find_similar(
    session: AsyncSession,
    fen: str,
    *,
    player: Player | None = None,
    max_distance: int = 4,
    limit: int = 20,
) -> list[PositionMatch]:
    """Return up to `limit` positions from this player's games close to `fen`.

    `max_distance` is the maximum Hamming distance on combined pawn bitboards.
    """
    target_board = chess.Board(fen)
    target_wp, target_bp = _pawn_bitboards(target_board)
    target_mat = _material_signature(target_board)

    where_clauses = []
    if player is not None:
        where_clauses.append(or_(
            Game.white_player_id == player.id,
            Game.black_player_id == player.id,
        ))

    # Scan all moves' fen_after that have similar material — we can prefilter
    # by occupancy count and bishop-pair-ish counts via per-piece counts
    # encoded in the FEN string. But cheapest: just walk our games. With ~20k
    # moves this is well under a second.
    q = (
        select(Move.game_id, Move.ply, Move.fen_after,
               MoveAnalysis.quality, MoveAnalysis.cp_loss)
        .outerjoin(MoveAnalysis, MoveAnalysis.move_id == Move.id)
    )
    if where_clauses:
        q = q.join(Game, Game.id == Move.game_id).where(*where_clauses)
    rows = (await session.execute(q)).all()

    matches: list[tuple[int, PositionMatch]] = []
    for game_id, ply, fen_after, quality, cp_loss in rows:
        try:
            b = chess.Board(fen_after)
        except Exception:
            continue
        # Cheap material guard
        if _material_signature(b) != target_mat:
            continue
        wp, bp = _pawn_bitboards(b)
        # Hamming on each side's pawns then sum
        d = _hamming(wp, target_wp) + _hamming(bp, target_bp)
        if d <= max_distance:
            matches.append((d, PositionMatch(
                game_id=game_id, ply=ply, fen=fen_after,
                distance=d,
                quality=str(quality) if quality else None,
                cp_loss=cp_loss,
            )))
    matches.sort(key=lambda t: t[0])
    return [m for _, m in matches[:limit]]

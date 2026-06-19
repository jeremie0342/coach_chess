"""Expose concrete squares for a few tactical motifs.

This is a thin wrapper around the geometric logic embedded in
`tactical_themes` — but returns the squares involved (so the Unity
frontend can draw lines between them) rather than booleans.
"""
from __future__ import annotations

from dataclasses import dataclass

import chess

from app.services.tactical_themes import (
    PIECE_VALUE,
    _enemy_pieces_attacked_by,
    _ray_directions,
    _step,
)


@dataclass
class Motif:
    kind: str
    attacker: str | None = None
    targets: list[str] | None = None
    pinned: str | None = None
    behind: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"kind": self.kind}
        if self.attacker is not None:
            d["attacker"] = self.attacker
        if self.targets is not None:
            d["targets"] = self.targets
        if self.pinned is not None:
            d["pinned"] = self.pinned
        if self.behind is not None:
            d["behind"] = self.behind
        return d


def missed_fork_geometry(fen_before: str, best_uci: str | None) -> Motif | None:
    if not best_uci:
        return None
    board = chess.Board(fen_before)
    try:
        best = chess.Move.from_uci(best_uci)
    except (ValueError, chess.InvalidMoveError):
        return None
    if best not in board.legal_moves:
        return None
    piece = board.piece_at(best.from_square)
    if not piece:
        return None
    board.push(best)
    targets = _enemy_pieces_attacked_by(board, best.to_square)
    if len(targets) < 2:
        return None
    attacker_val = PIECE_VALUE[piece.piece_type]
    higher = [t for t in targets if PIECE_VALUE[t[1].piece_type] > attacker_val]
    has_king = any(p.piece_type == chess.KING for _, p in targets)
    if not (higher or has_king):
        return None
    return Motif(
        kind="missed_fork",
        attacker=chess.square_name(best.to_square),
        targets=[chess.square_name(sq) for sq, _ in targets],
    )


def missed_pin_geometry(fen_before: str, best_uci: str | None) -> Motif | None:
    if not best_uci:
        return None
    board = chess.Board(fen_before)
    try:
        best = chess.Move.from_uci(best_uci)
    except (ValueError, chess.InvalidMoveError):
        return None
    if best not in board.legal_moves:
        return None
    piece = board.piece_at(best.from_square)
    if not piece or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return None
    board.push(best)
    attacker_sq = best.to_square
    for direction in _ray_directions(piece.piece_type):
        cur_sq = attacker_sq
        first_enemy = None
        while True:
            cur_sq = _step(cur_sq, direction)
            if cur_sq is None:
                break
            p = board.piece_at(cur_sq)
            if p is None:
                continue
            if p.color == piece.color:
                break
            if first_enemy is None:
                first_enemy = (cur_sq, p)
                continue
            front_val = PIECE_VALUE[first_enemy[1].piece_type]
            back_val = PIECE_VALUE[p.piece_type]
            if back_val > front_val:
                return Motif(
                    kind="missed_pin",
                    attacker=chess.square_name(attacker_sq),
                    pinned=chess.square_name(first_enemy[0]),
                    behind=chess.square_name(cur_sq),
                )
            break
    return None


def allowed_fork_geometry(
    fen_before: str, played_uci: str | None, pv_uci: list[str] | None
) -> Motif | None:
    """After the player's move, opponent's reply (pv[0] after our move)
    creates a fork on us."""
    if not played_uci or not pv_uci:
        return None
    board = chess.Board(fen_before)
    try:
        played = chess.Move.from_uci(played_uci)
    except (ValueError, chess.InvalidMoveError):
        return None
    if played not in board.legal_moves:
        return None
    board.push(played)
    # First move of pv after the played move is opponent's reply
    if not pv_uci:
        return None
    try:
        reply = chess.Move.from_uci(pv_uci[0])
    except (ValueError, chess.InvalidMoveError):
        return None
    if reply not in board.legal_moves:
        return None
    attacker_piece = board.piece_at(reply.from_square)
    if not attacker_piece:
        return None
    board.push(reply)
    targets = _enemy_pieces_attacked_by(board, reply.to_square)
    if len(targets) < 2:
        return None
    attacker_val = PIECE_VALUE[attacker_piece.piece_type]
    higher = [t for t in targets if PIECE_VALUE[t[1].piece_type] > attacker_val]
    has_king = any(p.piece_type == chess.KING for _, p in targets)
    if not (higher or has_king):
        return None
    return Motif(
        kind="allowed_fork",
        attacker=chess.square_name(reply.to_square),
        targets=[chess.square_name(sq) for sq, _ in targets],
    )


def collect_motifs(
    tags: list[str],
    fen_before: str,
    played_uci: str | None,
    best_uci: str | None,
    pv_uci: list[str] | None,
) -> list[Motif]:
    out: list[Motif] = []
    if "missed_fork" in tags:
        m = missed_fork_geometry(fen_before, best_uci)
        if m is not None:
            out.append(m)
    if "missed_pin" in tags:
        m = missed_pin_geometry(fen_before, best_uci)
        if m is not None:
            out.append(m)
    if "allowed_fork" in tags:
        m = allowed_fork_geometry(fen_before, played_uci, pv_uci)
        if m is not None:
            out.append(m)
    return out

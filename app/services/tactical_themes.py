"""Classify chess move blunders by tactical motif.

We work purely off board state — no extra Stockfish calls. Inputs:

  - fen_before     : the position the player faced
  - played_uci     : what the player chose (a blunder/mistake)
  - best_uci       : Stockfish's #1 move
  - pv_uci         : Stockfish's principal variation from `fen_before`
  - eval_cp_before : eval (player POV) before the move (cp)
  - eval_mate_before : mate score before the move (None if no mate)

Output: a list of theme tags applicable to this move.

Themes we detect:

  missed_mate_in_N      best line was mate in N
  missed_back_rank_mate variation of missed_mate_in_N where mate is on the
                        last rank against an unescapable king
  missed_fork           best move attacks ≥ 2 enemy pieces of which ≥ 1 is
                        higher value than the moving piece
  missed_pin            best move pins an enemy piece against a higher-value
                        piece on the same line (rook/bishop/queen attackers)
  missed_skewer         best move forces the higher-value piece to step away
                        revealing a lower-value piece behind it
  missed_discovered_attack the moving piece in the best move uncovers an
                        attacker behind it on the same line
  trapped_piece         after the played move, one of MY pieces is attacked
                        with no safe square (extends hanging_piece)
  allowed_fork          after the played move, opponent has a fork available
                        (opponent's best reply attacks ≥ 2 of MY pieces)

The detector is conservative: we tag a theme only when the geometric pattern
unambiguously matches. Better to miss a tag than to mislabel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import chess


PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


@dataclass
class ClassifyInput:
    fen_before: str
    played_uci: str
    best_uci: str | None
    pv_uci: list[str] | None
    eval_cp_before: int | None
    eval_mate_before: int | None


# ---------- Helper geometry ----------


def _line_squares_between(a: int, b: int) -> list[int]:
    """Squares strictly between a and b on the same rank/file/diagonal, or [] if none."""
    a_file, a_rank = chess.square_file(a), chess.square_rank(a)
    b_file, b_rank = chess.square_file(b), chess.square_rank(b)
    df = b_file - a_file
    dr = b_rank - a_rank
    if not (df == 0 or dr == 0 or abs(df) == abs(dr)):
        return []
    step_f = 0 if df == 0 else (1 if df > 0 else -1)
    step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
    f, r = a_file + step_f, a_rank + step_r
    out = []
    while (f, r) != (b_file, b_rank):
        out.append(chess.square(f, r))
        f += step_f
        r += step_r
    return out


def _attacks_from(board: chess.Board, sq: int) -> chess.SquareSet:
    """All squares the piece on `sq` actually attacks in the current position."""
    return board.attacks(sq)


def _enemy_pieces_attacked_by(board: chess.Board, sq: int) -> list[tuple[int, chess.Piece]]:
    piece = board.piece_at(sq)
    if not piece:
        return []
    out = []
    for tgt in _attacks_from(board, sq):
        target_piece = board.piece_at(tgt)
        if target_piece and target_piece.color != piece.color:
            out.append((tgt, target_piece))
    return out


# ---------- Theme tests ----------


def _missed_mate(pv_uci: list[str] | None, mate_score: int | None) -> str | None:
    if mate_score is not None and mate_score > 0:
        n = abs(mate_score)
        return f"missed_mate_in_{min(n, 5)}"
    return None


def _missed_back_rank_mate(
    fen_before: str, best_uci: str | None, mate_score: int | None
) -> bool:
    if not best_uci or mate_score is None or mate_score < 1 or mate_score > 2:
        return False
    board = chess.Board(fen_before)
    try:
        best = chess.Move.from_uci(best_uci)
    except (ValueError, chess.InvalidMoveError):
        return False
    if best not in board.legal_moves:
        return False
    board.push(best)
    if not board.is_check():
        return False
    opp_king = board.king(board.turn)
    if opp_king is None:
        return False
    king_rank = chess.square_rank(opp_king)
    # back rank for the defender: 0 if black, 7 if white
    expected_back = 7 if board.turn == chess.WHITE else 0
    return king_rank == expected_back


def _missed_fork(fen_before: str, best_uci: str | None) -> bool:
    if not best_uci:
        return False
    board = chess.Board(fen_before)
    try:
        best = chess.Move.from_uci(best_uci)
    except (ValueError, chess.InvalidMoveError):
        return False
    if best not in board.legal_moves:
        return False
    piece = board.piece_at(best.from_square)
    if not piece:
        return False
    board.push(best)
    targets = _enemy_pieces_attacked_by(board, best.to_square)
    if len(targets) < 2:
        return False
    attacker_val = PIECE_VALUE[piece.piece_type]
    # Require at least 1 target of strictly higher value, or king + something else
    higher = [t for _, t in targets if PIECE_VALUE[t.piece_type] > attacker_val]
    has_king = any(t.piece_type == chess.KING for _, t in targets)
    return bool(higher) or has_king


def _missed_pin(fen_before: str, best_uci: str | None) -> bool:
    """Best move creates a pin against a higher-value piece on the same line."""
    if not best_uci:
        return False
    board = chess.Board(fen_before)
    try:
        best = chess.Move.from_uci(best_uci)
    except (ValueError, chess.InvalidMoveError):
        return False
    if best not in board.legal_moves:
        return False
    piece = board.piece_at(best.from_square)
    if not piece or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    board.push(best)
    attacker_sq = best.to_square
    # Look along each ray from attacker, find the first enemy piece (the pinned),
    # then check if behind it on the same ray there's a higher-value enemy piece.
    for direction in _ray_directions(piece.piece_type):
        cur_sq = attacker_sq
        first_enemy: tuple[int, chess.Piece] | None = None
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
            # Second enemy on the same ray
            front_val = PIECE_VALUE[first_enemy[1].piece_type]
            back_val = PIECE_VALUE[p.piece_type]
            if back_val > front_val:
                return True
            break
    return False


def _missed_skewer(fen_before: str, best_uci: str | None) -> bool:
    """Best move attacks a high-value piece with a lower-value behind it.

    Skewer = pin reversed: front piece is the high-value one.
    """
    if not best_uci:
        return False
    board = chess.Board(fen_before)
    try:
        best = chess.Move.from_uci(best_uci)
    except (ValueError, chess.InvalidMoveError):
        return False
    if best not in board.legal_moves:
        return False
    piece = board.piece_at(best.from_square)
    if not piece or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    board.push(best)
    attacker_sq = best.to_square
    for direction in _ray_directions(piece.piece_type):
        cur_sq = attacker_sq
        first_enemy: tuple[int, chess.Piece] | None = None
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
            if front_val > back_val and front_val >= 5:  # rook or queen in front
                return True
            break
    return False


def _missed_discovered_attack(fen_before: str, best_uci: str | None) -> bool:
    """Best move clears a line for a friendly piece behind, attacking enemy material."""
    if not best_uci:
        return False
    board = chess.Board(fen_before)
    try:
        best = chess.Move.from_uci(best_uci)
    except (ValueError, chess.InvalidMoveError):
        return False
    if best not in board.legal_moves:
        return False
    from_sq = best.from_square
    moving_piece = board.piece_at(from_sq)
    if not moving_piece:
        return False
    # For each long-range friendly piece, check if the from_sq was on its ray
    # and target an enemy piece beyond.
    for sq, p in board.piece_map().items():
        if p.color != moving_piece.color or p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        if sq == from_sq:
            continue
        # Check if from_sq is between attacker and an enemy piece (on a line)
        for direction in _ray_directions(p.piece_type):
            cur = sq
            saw_from = False
            while True:
                cur = _step(cur, direction)
                if cur is None:
                    break
                if cur == from_sq:
                    saw_from = True
                    continue
                piece_here = board.piece_at(cur)
                if piece_here is None:
                    continue
                if saw_from and piece_here.color != moving_piece.color:
                    # The discovered attack reveals THIS enemy piece
                    if PIECE_VALUE[piece_here.piece_type] >= 3:
                        return True
                break
    return False


def _trapped_piece_after_played(
    fen_before: str, played_uci: str
) -> bool:
    """After the played move, one of MY non-pawn pieces is attacked and has no safe square."""
    board = chess.Board(fen_before)
    try:
        played = chess.Move.from_uci(played_uci)
    except (ValueError, chess.InvalidMoveError):
        return False
    if played not in board.legal_moves:
        return False
    my_color = board.turn
    board.push(played)
    # Now it's opponent to move; we check each of MY pieces
    for sq, p in board.piece_map().items():
        if p.color != my_color or p.piece_type == chess.PAWN:
            continue
        if not board.is_attacked_by(not my_color, sq):
            continue
        # Try every legal move OF ME from a sub-board (simulating quiet check)
        # Approach: temporarily flip turn and enumerate moves of that piece
        tmp = board.copy(stack=False)
        tmp.turn = my_color
        safe = False
        for m in tmp.legal_moves:
            if m.from_square != sq:
                continue
            tmp2 = tmp.copy(stack=False)
            tmp2.push(m)
            if not tmp2.is_attacked_by(not my_color, m.to_square):
                safe = True
                break
            # or captures with net positive for us
            target = board.piece_at(m.to_square)
            if target and PIECE_VALUE[target.piece_type] >= PIECE_VALUE[p.piece_type]:
                safe = True
                break
        if not safe:
            return True
    return False


def _allowed_fork(fen_before: str, played_uci: str, pv_uci: list[str] | None) -> bool:
    """After the played move, opponent's best reply forks two of MY pieces."""
    if not pv_uci or len(pv_uci) < 1:
        return False
    board = chess.Board(fen_before)
    try:
        played = chess.Move.from_uci(played_uci)
    except (ValueError, chess.InvalidMoveError):
        return False
    if played not in board.legal_moves:
        return False
    board.push(played)
    # Use the principal variation NEXT move as the opponent's best reply.
    if not pv_uci:
        return False
    # PV from the original position; after our move it now starts at index >= 0.
    # If we played the best move (pv_uci[0]), opponent's response is pv_uci[1].
    # If we played a different move, we don't know the opponent's exact best — use
    # board.is_attacked detection on what is now legal for them.
    # Simpler heuristic: enumerate opponent legal moves; look for any that creates a fork.
    opp_color = board.turn
    for m in board.legal_moves:
        piece = board.piece_at(m.from_square)
        if not piece:
            continue
        tmp = board.copy(stack=False)
        tmp.push(m)
        attacked = []
        for tgt in tmp.attacks(m.to_square):
            t_piece = tmp.piece_at(tgt)
            if t_piece and t_piece.color != opp_color and PIECE_VALUE[t_piece.piece_type] >= 3:
                attacked.append(t_piece)
        if len(attacked) >= 2:
            return True
    return False


# ---------- Ray helpers ----------


_BISHOP_DIRS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
_ROOK_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_QUEEN_DIRS = _BISHOP_DIRS + _ROOK_DIRS


def _ray_directions(piece_type: chess.PieceType) -> tuple[tuple[int, int], ...]:
    if piece_type == chess.BISHOP:
        return _BISHOP_DIRS
    if piece_type == chess.ROOK:
        return _ROOK_DIRS
    if piece_type == chess.QUEEN:
        return _QUEEN_DIRS
    return ()


def _step(sq: int, direction: tuple[int, int]) -> int | None:
    df, dr = direction
    f = chess.square_file(sq) + df
    r = chess.square_rank(sq) + dr
    if 0 <= f < 8 and 0 <= r < 8:
        return chess.square(f, r)
    return None


# ---------- Public entry point ----------


def classify_themes(inp: ClassifyInput) -> list[str]:
    """Return the list of tactical theme tags applicable to this move."""
    tags: list[str] = []
    mate_tag = _missed_mate(inp.pv_uci, inp.eval_mate_before)
    if mate_tag:
        tags.append(mate_tag)
        if _missed_back_rank_mate(inp.fen_before, inp.best_uci, inp.eval_mate_before):
            tags.append("missed_back_rank_mate")
    if _missed_fork(inp.fen_before, inp.best_uci):
        tags.append("missed_fork")
    if _missed_pin(inp.fen_before, inp.best_uci):
        tags.append("missed_pin")
    if _missed_skewer(inp.fen_before, inp.best_uci):
        tags.append("missed_skewer")
    if _missed_discovered_attack(inp.fen_before, inp.best_uci):
        tags.append("missed_discovered_attack")
    if _trapped_piece_after_played(inp.fen_before, inp.played_uci):
        tags.append("trapped_piece")
    if _allowed_fork(inp.fen_before, inp.played_uci, inp.pv_uci):
        tags.append("allowed_fork")
    return tags

"""Pawn-structure feature detection for a single position.

We return a `PawnStructure` record describing the classical features that
matter for middlegame strategy. Pure board logic — no Stockfish.

Detected (per color):
  isolated        — pawns with no friendly pawn on adjacent files
  doubled         — files with >= 2 friendly pawns
  backward        — pawns that can't be supported by friendly pawns, on a
                    half-open file towards the enemy
  passed          — pawns with no enemy pawn ahead on same or adjacent files
  iqp             — isolated queen pawn (special case, file d)
  hanging         — two adjacent pawns, both isolated from other pawns
  closed_files    — files with both white and black pawns blocking each other
  semi_open_files — files with only one side's pawns
  open_files      — files with no pawn

`signature()` returns a compact tuple usable as a dict key.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import chess


FILE_LETTERS = "abcdefgh"


@dataclass
class PawnStructure:
    fen: str
    iqp_white: bool = False
    iqp_black: bool = False
    isolated_files_white: list[str] = field(default_factory=list)
    isolated_files_black: list[str] = field(default_factory=list)
    doubled_files_white: list[str] = field(default_factory=list)
    doubled_files_black: list[str] = field(default_factory=list)
    backward_files_white: list[str] = field(default_factory=list)
    backward_files_black: list[str] = field(default_factory=list)
    passed_files_white: list[str] = field(default_factory=list)
    passed_files_black: list[str] = field(default_factory=list)
    hanging_white: bool = False
    hanging_black: bool = False
    open_files: list[str] = field(default_factory=list)
    semi_open_files_white: list[str] = field(default_factory=list)
    semi_open_files_black: list[str] = field(default_factory=list)

    def tags(self) -> list[str]:
        out: list[str] = []
        if self.iqp_white: out.append("iqp_white")
        if self.iqp_black: out.append("iqp_black")
        if self.hanging_white: out.append("hanging_white")
        if self.hanging_black: out.append("hanging_black")
        if self.doubled_files_white: out.append("doubled_white")
        if self.doubled_files_black: out.append("doubled_black")
        if self.passed_files_white: out.append("passed_white")
        if self.passed_files_black: out.append("passed_black")
        if self.isolated_files_white: out.append("isolated_white")
        if self.isolated_files_black: out.append("isolated_black")
        if self.backward_files_white: out.append("backward_white")
        if self.backward_files_black: out.append("backward_black")
        if len(self.open_files) >= 2:
            out.append("multi_open_files")
        return out

    def signature(self) -> tuple:
        return (
            self.iqp_white, self.iqp_black,
            tuple(self.passed_files_white), tuple(self.passed_files_black),
            tuple(self.doubled_files_white), tuple(self.doubled_files_black),
            self.hanging_white, self.hanging_black,
            tuple(self.open_files),
        )


def _pawn_files(board: chess.Board, color: chess.Color) -> dict[int, list[int]]:
    """Return {file_index: [rank_indices]} for pawns of `color`."""
    out: dict[int, list[int]] = {}
    for sq in board.pieces(chess.PAWN, color):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        out.setdefault(f, []).append(r)
    return out


def _is_passed(file_: int, rank: int, color: chess.Color, opp_pawns: dict[int, list[int]]) -> bool:
    """Pawn on (file_, rank) of `color` is passed iff no enemy pawn on
    file_ or adjacent files ahead of it.
    """
    direction = 1 if color == chess.WHITE else -1
    for df in (-1, 0, 1):
        nf = file_ + df
        if not (0 <= nf < 8):
            continue
        for r in opp_pawns.get(nf, []):
            if direction * (r - rank) > 0:
                return False
    return True


def _is_isolated(file_: int, own_pawns: dict[int, list[int]]) -> bool:
    return (file_ - 1) not in own_pawns and (file_ + 1) not in own_pawns


def _is_backward(
    file_: int, rank: int, color: chess.Color,
    own_pawns: dict[int, list[int]], opp_pawns: dict[int, list[int]],
) -> bool:
    """A pawn is backward iff no friendly pawn is on adjacent files BEHIND
    or LEVEL with it, and the square in front is controlled by an enemy pawn.
    """
    direction = 1 if color == chess.WHITE else -1
    # Friendly pawn at level/behind on adjacent file?
    for df in (-1, 1):
        nf = file_ + df
        if not (0 <= nf < 8):
            continue
        for r in own_pawns.get(nf, []):
            if direction * (r - rank) <= 0:
                return False
    # Square in front controlled by an enemy pawn?
    front_rank = rank + direction
    if not (0 <= front_rank < 8):
        return False
    for df in (-1, 1):
        nf = file_ + df
        if not (0 <= nf < 8):
            continue
        # Enemy pawn that would attack our front-square is one rank ahead of front,
        # because pawns attack diagonally one rank.
        attacker_rank = front_rank + direction
        if attacker_rank in opp_pawns.get(nf, []):
            return True
    return False


def analyse(fen: str) -> PawnStructure:
    board = chess.Board(fen)
    w_pawns = _pawn_files(board, chess.WHITE)
    b_pawns = _pawn_files(board, chess.BLACK)

    s = PawnStructure(fen=fen)

    # Doubled
    s.doubled_files_white = [FILE_LETTERS[f] for f, rs in w_pawns.items() if len(rs) >= 2]
    s.doubled_files_black = [FILE_LETTERS[f] for f, rs in b_pawns.items() if len(rs) >= 2]

    # Isolated
    iso_w = [f for f in w_pawns if _is_isolated(f, w_pawns)]
    iso_b = [f for f in b_pawns if _is_isolated(f, b_pawns)]
    s.isolated_files_white = [FILE_LETTERS[f] for f in iso_w]
    s.isolated_files_black = [FILE_LETTERS[f] for f in iso_b]

    # IQP (isolated queen pawn)
    s.iqp_white = (3 in iso_w and 3 in w_pawns)
    s.iqp_black = (3 in iso_b and 3 in b_pawns)

    # Passed
    pas_w, pas_b = set(), set()
    for f, ranks in w_pawns.items():
        for r in ranks:
            if _is_passed(f, r, chess.WHITE, b_pawns):
                pas_w.add(f)
    for f, ranks in b_pawns.items():
        for r in ranks:
            if _is_passed(f, r, chess.BLACK, w_pawns):
                pas_b.add(f)
    s.passed_files_white = [FILE_LETTERS[f] for f in sorted(pas_w)]
    s.passed_files_black = [FILE_LETTERS[f] for f in sorted(pas_b)]

    # Backward
    back_w, back_b = [], []
    for f, ranks in w_pawns.items():
        for r in ranks:
            if _is_backward(f, r, chess.WHITE, w_pawns, b_pawns):
                back_w.append(f); break
    for f, ranks in b_pawns.items():
        for r in ranks:
            if _is_backward(f, r, chess.BLACK, b_pawns, w_pawns):
                back_b.append(f); break
    s.backward_files_white = [FILE_LETTERS[f] for f in back_w]
    s.backward_files_black = [FILE_LETTERS[f] for f in back_b]

    # Hanging (two adjacent isolated pawns on the 4th/5th rank are the classical case)
    s.hanging_white = _has_hanging(iso_w, w_pawns)
    s.hanging_black = _has_hanging(iso_b, b_pawns)

    # Open / semi-open files
    open_files: list[str] = []
    sof_w: list[str] = []
    sof_b: list[str] = []
    for f in range(8):
        has_w = f in w_pawns
        has_b = f in b_pawns
        if not has_w and not has_b:
            open_files.append(FILE_LETTERS[f])
        elif has_w and not has_b:
            sof_b.append(FILE_LETTERS[f])   # semi-open for black (no black pawn)
        elif has_b and not has_w:
            sof_w.append(FILE_LETTERS[f])
    s.open_files = open_files
    s.semi_open_files_white = sof_w
    s.semi_open_files_black = sof_b
    return s


def _has_hanging(isolated: list[int], own_pawns: dict[int, list[int]]) -> bool:
    """Two isolated pawns on adjacent files = hanging pawn pair."""
    iso_set = set(isolated)
    for f in iso_set:
        if (f + 1) in iso_set:
            return True
    return False

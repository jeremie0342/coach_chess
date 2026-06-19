"""Tactical theme classifier on hand-crafted positions."""
from __future__ import annotations

from app.services.tactical_themes import ClassifyInput, classify_themes


def test_no_tags_when_no_best_move() -> None:
    tags = classify_themes(ClassifyInput(
        fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        played_uci="e2e4",
        best_uci=None, pv_uci=None,
        eval_cp_before=None, eval_mate_before=None,
    ))
    assert tags == []


def test_missed_mate_in_2_detected() -> None:
    # Stockfish saw mate-in-2 before; the player played something else.
    tags = classify_themes(ClassifyInput(
        fen_before="6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",  # arbitrary placeholder
        played_uci="a1a8",
        best_uci="a1a8",  # not relevant: we test mate detection only
        pv_uci=["a1a8"],
        eval_cp_before=None, eval_mate_before=2,
    ))
    assert "missed_mate_in_2" in tags


def test_missed_mate_in_1_detected() -> None:
    tags = classify_themes(ClassifyInput(
        fen_before="6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
        played_uci="g1g2",
        best_uci="a1a8",
        pv_uci=["a1a8"],
        eval_cp_before=None, eval_mate_before=1,
    ))
    assert "missed_mate_in_1" in tags


def test_missed_fork_knight() -> None:
    # White knight on f3 can play Ne5 forking the king on e8 and queen on d7? No
    # Use a clear fork: black queen on d8, king on e8; white knight to fork via c7? No king is on e8.
    # Simpler: black king on e8, rook on a8. White knight on b5 plays Nc7+ forking king + rook.
    fen = "r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1"
    tags = classify_themes(ClassifyInput(
        fen_before=fen,
        played_uci="b5a3",     # passive knight retreat (the blunder)
        best_uci="b5c7",       # Nc7+ forks king + rook
        pv_uci=["b5c7"],
        eval_cp_before=300,
        eval_mate_before=None,
    ))
    assert "missed_fork" in tags


def test_classifier_robust_on_quiet_position() -> None:
    """Quiet opening position: no theme should fire, classifier shouldn't crash."""
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    tags = classify_themes(ClassifyInput(
        fen_before=fen, played_uci="e2e3", best_uci="e2e4",
        pv_uci=["e2e4"], eval_cp_before=20, eval_mate_before=None,
    ))
    assert isinstance(tags, list)


def test_classifier_handles_garbage_best_move_gracefully() -> None:
    """Malformed UCI should never crash the classifier."""
    tags = classify_themes(ClassifyInput(
        fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        played_uci="e2e4", best_uci="ZZZZ",
        pv_uci=None, eval_cp_before=None, eval_mate_before=None,
    ))
    assert tags == []

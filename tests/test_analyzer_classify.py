"""Quality classification thresholds in analyzer.classify."""
from __future__ import annotations

import pytest

from app.models.analysis import MoveQuality
from app.services.analyzer import classify


@pytest.mark.parametrize("cp_loss, expected", [
    (0, MoveQuality.BEST),
    (5, MoveQuality.BEST),
    (10, MoveQuality.BEST),
    (11, MoveQuality.EXCELLENT),
    (30, MoveQuality.EXCELLENT),
    (60, MoveQuality.GOOD),
    (100, MoveQuality.INACCURACY),
    (150, MoveQuality.INACCURACY),
    (200, MoveQuality.MISTAKE),
    (300, MoveQuality.MISTAKE),
    (301, MoveQuality.BLUNDER),
    (1000, MoveQuality.BLUNDER),
])
def test_classify_thresholds(cp_loss: int, expected: MoveQuality) -> None:
    assert classify(cp_loss) == expected


def test_classify_none_is_good() -> None:
    assert classify(None) == MoveQuality.GOOD

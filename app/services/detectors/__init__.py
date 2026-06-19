from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding
from app.services.detectors.aggregates import (
    ColorImbalanceDetector,
    EarlyLossDetector,
    LowWinrateOpeningDetector,
    TimeTroubleDetector,
    WeakAgainstFirstMoveDetector,
)
from app.services.detectors.phase_blunders import (
    EndgameBlunderDetector,
    MiddlegameBlunderDetector,
    OpeningBlunderDetector,
)
from app.services.detectors.hanging_piece import HangingPieceDetector
from app.services.detectors.missed_tactic import MissedTacticDetector
from app.services.detectors.tactical_themes_detector import TacticalThemeDetector
from app.services.detectors.pawn_structure_detector import PawnStructureDetector

DEFAULT_DETECTORS: list[Detector] = [
    # No-Stockfish-needed
    LowWinrateOpeningDetector(),
    WeakAgainstFirstMoveDetector(),
    ColorImbalanceDetector(),
    EarlyLossDetector(),
    TimeTroubleDetector(),
    PawnStructureDetector(),
    # Stockfish-driven
    OpeningBlunderDetector(),
    MiddlegameBlunderDetector(),
    EndgameBlunderDetector(),
    HangingPieceDetector(),
    MissedTacticDetector(),
    TacticalThemeDetector(),
]

__all__ = [
    "Detector",
    "DetectorContext",
    "WeaknessFinding",
    "DEFAULT_DETECTORS",
]

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ExerciseKind(StrEnum):
    TACTIC = "tactic"
    ENDGAME = "endgame"
    OPENING = "opening"
    POSITIONAL = "positional"
    CALCULATION = "calculation"


class ExerciseSource(StrEnum):
    BLUNDER = "blunder"        # from my own analyzed games
    LICHESS = "lichess"        # from the lichess public puzzle dataset
    MANUAL = "manual"          # hand-crafted / pasted


class Exercise(Base, TimestampMixin):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[ExerciseSource] = mapped_column(String(16), default=ExerciseSource.BLUNDER, index=True)
    lichess_id: Mapped[str | None] = mapped_column(String(16), unique=True, index=True)
    source_game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"))
    source_move_id: Mapped[int | None] = mapped_column(
        ForeignKey("moves.id", ondelete="CASCADE"), unique=True, index=True
    )
    source_weakness_id: Mapped[int | None] = mapped_column(ForeignKey("weaknesses.id", ondelete="SET NULL"))

    kind: Mapped[ExerciseKind] = mapped_column(String(16), index=True)
    title: Mapped[str | None] = mapped_column(String(256))
    fen: Mapped[str] = mapped_column(String(128))
    side_to_move: Mapped[str] = mapped_column(String(1))
    solution_uci: Mapped[list[str]] = mapped_column(JSONB)

    difficulty: Mapped[int] = mapped_column(default=1000, index=True)
    rating_deviation: Mapped[int | None]
    popularity: Mapped[int | None]
    nb_plays: Mapped[int | None]
    theme_tags: Mapped[list[str] | None] = mapped_column(JSONB)
    opening_tags: Mapped[list[str] | None] = mapped_column(JSONB)
    explanation: Mapped[str | None] = mapped_column(Text)

    # SR state
    sr_ease: Mapped[float] = mapped_column(default=2.5)
    sr_interval_days: Mapped[int] = mapped_column(default=0)
    sr_repetitions: Mapped[int] = mapped_column(default=0)
    sr_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sr_last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[int] = mapped_column(default=0)
    successes: Mapped[int] = mapped_column(default=0)

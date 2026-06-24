from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OpeningProgressStatus(StrEnum):
    ACTIVE = "active"
    MASTERED = "mastered"


# 7 daily perfect runs in a row -> mastery.
MASTERY_STREAK = 7


class OpeningProgress(Base, TimestampMixin):
    """Tracks a user's mastery of a specific opening trainer variant.

    Lifecycle:
      - ACTIVE : daily drill expected. A perfect run (no wrong move) bumps the
        streak by 1 per day. A failed attempt resets streak to 0.
      - MASTERED : reached MASTERY_STREAK consecutive perfect days. The coach
        rotates to another active variant in the same color slot.
    """

    __tablename__ = "opening_progress"
    __table_args__ = (
        UniqueConstraint("player_id", "opening_key", name="uq_opening_progress_player_key"),
        Index("ix_opening_progress_player_status", "player_id", "user_color", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)

    opening_key: Mapped[str] = mapped_column(String(64), index=True)
    base_name: Mapped[str] = mapped_column(String(64))
    user_color: Mapped[str] = mapped_column(String(8))

    status: Mapped[OpeningProgressStatus] = mapped_column(String(16), default=OpeningProgressStatus.ACTIVE)
    streak_days: Mapped[int] = mapped_column(default=0)
    last_perfect_date: Mapped[date | None] = mapped_column(Date)
    best_streak: Mapped[int] = mapped_column(default=0)

    attempts: Mapped[int] = mapped_column(default=0)
    perfect_runs: Mapped[int] = mapped_column(default=0)
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

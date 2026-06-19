from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DailyItemKind(StrEnum):
    REPERTOIRE_DRILL = "repertoire_drill"      # SM-2 cards
    PUZZLE_FOCUSED = "puzzle_focused"           # Lichess puzzles, theme-filtered
    BLUNDER_REVIEW = "blunder_review"           # my own past blunders
    ENDGAME_PRACTICE = "endgame_practice"       # endgame puzzles
    OPENING_STUDY = "opening_study"             # repertoire study (no SM-2 grading)
    COACH_NOTE = "coach_note"                   # narrative note, no drill


class DailyPlan(Base, TimestampMixin):
    __tablename__ = "daily_plans"
    __table_args__ = (
        UniqueConstraint("player_id", "plan_date", name="uq_daily_plan_player_date"),
        Index("ix_daily_plans_plan_date", "plan_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    plan_date: Mapped[date] = mapped_column(Date)
    target_minutes: Mapped[int] = mapped_column(default=30)
    coach_message: Mapped[str | None] = mapped_column(Text)
    weakness_focus: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items = relationship(
        "DailyPlanItem",
        back_populates="plan",
        order_by="DailyPlanItem.order_index",
        cascade="all, delete-orphan",
    )


class DailyPlanItem(Base):
    __tablename__ = "daily_plan_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("daily_plans.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int]

    kind: Mapped[DailyItemKind] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(256))
    target_count: Mapped[int]
    estimated_minutes: Mapped[int]
    filters: Mapped[dict | None] = mapped_column(JSONB)
    rationale: Mapped[str | None] = mapped_column(Text)

    completed_count: Mapped[int] = mapped_column(default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan = relationship("DailyPlan", back_populates="items")

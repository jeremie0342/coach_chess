from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class WeeklyReport(Base, TimestampMixin):
    """Auto-generated weekly debrief.

    One row per (player_id, week_start). The cron job upserts each Sunday.
    """
    __tablename__ = "weekly_reports"
    __table_args__ = (
        UniqueConstraint("player_id", "week_start", name="uq_weekly_report_player_week"),
        Index("ix_weekly_reports_week_start", "week_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Headline numbers — kept structured for charts
    games_played: Mapped[int] = mapped_column(default=0)
    elo_delta: Mapped[int] = mapped_column(default=0)
    puzzles_solved: Mapped[int] = mapped_column(default=0)
    rep_cards_reviewed: Mapped[int] = mapped_column(default=0)
    plans_completed: Mapped[int] = mapped_column(default=0)
    blunders_this_week: Mapped[int] = mapped_column(default=0)

    weakness_deltas: Mapped[dict | None] = mapped_column(JSONB)
    top_focus_for_next_week: Mapped[str | None] = mapped_column(Text)
    narrative: Mapped[str | None] = mapped_column(Text)

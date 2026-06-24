"""Persistent live-debrief snapshots.

Each /coach/live_debrief call produces a row here so the user can list past
debriefs and reopen them without re-running the analysis.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LiveDebriefReport(Base):
    __tablename__ = "live_debrief_reports"
    __table_args__ = (
        Index("ix_live_debrief_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    # The complete /coach/live_debrief response dict.
    payload: Mapped[dict] = mapped_column(JSONB)
    # Compact subset for the list view.
    summary: Mapped[dict | None] = mapped_column(JSONB)
    # Free-text title (defaults to "{opening} — {date}")
    title: Mapped[str | None] = mapped_column(String(256))

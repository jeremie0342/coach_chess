"""Persistent snapshots of /coach/scout runs.

Each scout call produces a row here so the user can:
  - list previously scouted opponents
  - re-open the latest report instantly (no recompute)
  - compare snapshots over time (rating delta, new/disappeared weaknesses,
    opening preference shifts, recent form trend)
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScoutSnapshot(Base):
    __tablename__ = "scout_snapshots"
    __table_args__ = (
        Index("ix_scout_snapshots_user_time", "opponent_username", "scouted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opponent_username: Mapped[str] = mapped_column(String(64), index=True)
    scouted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    # The complete /coach/scout response dict, as returned to the frontend.
    payload: Mapped[dict] = mapped_column(JSONB)
    # Extracted top-level fields for cheap listing without parsing payload.
    summary: Mapped[dict | None] = mapped_column(JSONB)

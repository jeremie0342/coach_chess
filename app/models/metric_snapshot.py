from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MetricSnapshot(Base, TimestampMixin):
    """Daily-ish snapshot of where the player stands. Used to draw progression curves.

    One row per snapshot (typically once a day via the arq snapshot task).
    Fields kept loose-JSON to avoid migrations every time a new metric is added.
    """
    __tablename__ = "metric_snapshots"
    __table_args__ = (
        Index("ix_metric_snapshots_player_taken", "player_id", "taken_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Top-line ratings
    rating_rapid: Mapped[int | None]
    rating_blitz: Mapped[int | None]
    rating_bullet: Mapped[int | None]

    # Game counts
    games_total: Mapped[int] = mapped_column(default=0)
    games_30d: Mapped[int] = mapped_column(default=0)
    games_7d: Mapped[int] = mapped_column(default=0)

    # Winrate
    winrate_white: Mapped[float | None]
    winrate_black: Mapped[float | None]

    # Training engagement
    exercises_solved_total: Mapped[int] = mapped_column(default=0)
    exercises_solved_7d: Mapped[int] = mapped_column(default=0)
    rep_cards_reviewed_7d: Mapped[int] = mapped_column(default=0)
    plans_completed_7d: Mapped[int] = mapped_column(default=0)

    # Loose blobs for flexibility
    weakness_severities: Mapped[dict | None] = mapped_column(JSONB)        # {category: severity}
    puzzles_solved_by_theme: Mapped[dict | None] = mapped_column(JSONB)    # {theme: count}
    repertoire_due: Mapped[int | None]
    exercises_due: Mapped[int | None]

    extras: Mapped[dict | None] = mapped_column(JSONB)

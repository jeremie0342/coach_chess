from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PlayerRepertoireEntry(Base, TimestampMixin):
    """An opening the user has explicitly added to their personal repertoire.

    Distinct from `OpeningProgress` (mastery streak per-variant): this table
    is the user's curated list — "these are the openings I want to learn".
    The opening trainer's mastery rotation can still operate independently.
    """

    __tablename__ = "player_repertoire_entries"
    __table_args__ = (
        UniqueConstraint("player_id", "opening_key", name="uq_player_repertoire_entry"),
        Index("ix_player_repertoire_color", "player_id", "user_color"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)

    opening_key: Mapped[str] = mapped_column(String(64))
    base_name: Mapped[str] = mapped_column(String(64))
    user_color: Mapped[str] = mapped_column(String(8))

    position: Mapped[int] = mapped_column(default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.utcnow(),
    )

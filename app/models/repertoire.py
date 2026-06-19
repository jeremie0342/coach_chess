from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class RepertoireColor(StrEnum):
    WHITE = "white"
    BLACK = "black"


class RepertoireNode(Base, TimestampMixin):
    """A node in the user's opening repertoire tree.

    A node represents a position (FEN) and the recommended move from it.
    Children are the possible opponent replies and our prepared responses.
    """

    __tablename__ = "repertoire_nodes"
    __table_args__ = (
        Index("ix_repertoire_color_fen", "color", "fen"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("repertoire_nodes.id", ondelete="CASCADE"), index=True
    )

    color: Mapped[RepertoireColor] = mapped_column(String(8))
    fen: Mapped[str] = mapped_column(String(128), index=True)

    move_uci: Mapped[str | None] = mapped_column(String(8))
    move_san: Mapped[str | None] = mapped_column(String(10))

    is_my_move: Mapped[bool] = mapped_column(default=False)
    is_main_line: Mapped[bool] = mapped_column(default=True)

    label: Mapped[str | None] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str | None] = mapped_column(Text)
    traps: Mapped[list[dict] | None] = mapped_column(JSONB)

    # Lichess masters DB annotations (refreshed periodically)
    gm_total_games: Mapped[int | None]
    gm_moves: Mapped[list[dict] | None] = mapped_column(JSONB)   # [{uci, san, games, score_white, ...}]
    gm_my_move_score: Mapped[float | None]                       # my move's score in masters DB
    gm_my_move_share: Mapped[float | None]                       # my move's fraction of GM games
    gm_annotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Spaced repetition state (SM-2 style)
    sr_ease: Mapped[float] = mapped_column(default=2.5)
    sr_interval_days: Mapped[int] = mapped_column(default=0)
    sr_repetitions: Mapped[int] = mapped_column(default=0)
    sr_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sr_last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    parent = relationship("RepertoireNode", remote_side="RepertoireNode.id", backref="children")

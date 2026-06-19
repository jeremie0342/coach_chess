from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class PositionSessionStatus(StrEnum):
    ACTIVE = "active"
    USER_WON = "user_won"
    USER_LOST = "user_lost"
    DRAW = "draw"
    ABANDONED = "abandoned"


class PositionSession(Base, TimestampMixin):
    """A user-vs-Stockfish session played out from a given FEN."""

    __tablename__ = "position_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )

    title: Mapped[str | None] = mapped_column(String(256))
    starting_fen: Mapped[str] = mapped_column(String(128))
    current_fen: Mapped[str] = mapped_column(String(128))
    user_color: Mapped[str] = mapped_column(String(8))  # 'white' | 'black'

    sf_skill_level: Mapped[int] = mapped_column(default=10)   # 0..20
    sf_elo: Mapped[int | None]
    sf_depth: Mapped[int] = mapped_column(default=12)

    status: Mapped[PositionSessionStatus] = mapped_column(
        String(16), default=PositionSessionStatus.ACTIVE, index=True
    )
    result_reason: Mapped[str | None] = mapped_column(String(64))
    final_ply: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Where the position came from, for context (e.g. a puzzle, an endgame, my own game)
    source: Mapped[str | None] = mapped_column(String(32))
    source_ref: Mapped[dict | None] = mapped_column(JSONB)

    moves = relationship(
        "PositionSessionMove",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PositionSessionMove.ply",
    )


class PositionSessionMove(Base):
    __tablename__ = "position_session_moves"
    __table_args__ = (
        Index("ix_pos_sess_moves_session_ply", "session_id", "ply", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("position_sessions.id", ondelete="CASCADE"), index=True
    )
    ply: Mapped[int]
    is_user: Mapped[bool]
    uci: Mapped[str] = mapped_column(String(8))
    san: Mapped[str] = mapped_column(String(10))
    fen_after: Mapped[str] = mapped_column(String(128))
    eval_cp_after: Mapped[int | None]
    eval_mate_after: Mapped[int | None]

    session = relationship("PositionSession", back_populates="moves")

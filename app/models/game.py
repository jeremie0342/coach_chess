from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class GameResult(StrEnum):
    WHITE_WIN = "1-0"
    BLACK_WIN = "0-1"
    DRAW = "1/2-1/2"
    UNKNOWN = "*"


class TimeControlCategory(StrEnum):
    BULLET = "bullet"
    BLITZ = "blitz"
    RAPID = "rapid"
    CLASSICAL = "classical"
    DAILY = "daily"


class Game(Base, TimestampMixin):
    __tablename__ = "games"
    __table_args__ = (
        Index("ix_games_played_at", "played_at"),
        # Note: ix_games_eco is created by `index=True` on the `eco` column below
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="chess.com")
    url: Mapped[str | None] = mapped_column(String(512))

    white_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    black_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    white_rating: Mapped[int | None]
    black_rating: Mapped[int | None]

    result: Mapped[GameResult] = mapped_column(String(8))
    termination: Mapped[str | None] = mapped_column(String(64))

    time_control: Mapped[str | None] = mapped_column(String(32))
    time_class: Mapped[TimeControlCategory | None] = mapped_column(String(16))
    rated: Mapped[bool] = mapped_column(default=True)

    eco: Mapped[str | None] = mapped_column(String(8), index=True)
    opening_name: Mapped[str | None] = mapped_column(String(256))
    opening_id: Mapped[int | None] = mapped_column(ForeignKey("openings.id"))

    pgn: Mapped[str] = mapped_column(Text)
    initial_fen: Mapped[str | None] = mapped_column(String(128))
    ply_count: Mapped[int] = mapped_column(default=0)

    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict | None] = mapped_column(JSONB)

    analysis_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set the first time the user opens this game in the "Lab" (Game Review).
    # Used by daily plan auto-credit to know if a review item has been honored.
    lab_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Out-of-book = first ply where the played move is no longer recognised
    # theory in our openings table. For the player's own moves only.
    my_out_of_book_ply: Mapped[int | None]
    opp_out_of_book_ply: Mapped[int | None]
    deepest_opening_id: Mapped[int | None] = mapped_column(ForeignKey("openings.id"))

    white_player = relationship("Player", back_populates="games_white", foreign_keys=[white_player_id])
    black_player = relationship("Player", back_populates="games_black", foreign_keys=[black_player_id])
    moves = relationship("Move", back_populates="game", order_by="Move.ply", cascade="all, delete-orphan")
    opening = relationship("Opening", foreign_keys=[opening_id])
    deepest_opening = relationship("Opening", foreign_keys=[deepest_opening_id])

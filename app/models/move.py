from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Move(Base):
    __tablename__ = "moves"
    __table_args__ = (
        Index("ix_moves_game_ply", "game_id", "ply", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)

    ply: Mapped[int]
    move_number: Mapped[int]
    is_white: Mapped[bool]

    san: Mapped[str] = mapped_column(String(10))
    uci: Mapped[str] = mapped_column(String(8))

    fen_before: Mapped[str] = mapped_column(String(128))
    fen_after: Mapped[str] = mapped_column(String(128))

    clock_seconds: Mapped[float | None]

    game = relationship("Game", back_populates="moves")
    analysis = relationship("MoveAnalysis", back_populates="move", uselist=False, cascade="all, delete-orphan")

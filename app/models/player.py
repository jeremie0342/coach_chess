from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Player(Base, TimestampMixin):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    chesscom_username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    is_me: Mapped[bool] = mapped_column(default=False, index=True)

    games_white = relationship(
        "Game", back_populates="white_player", foreign_keys="Game.white_player_id"
    )
    games_black = relationship(
        "Game", back_populates="black_player", foreign_keys="Game.black_player_id"
    )

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Opening(Base):
    __tablename__ = "openings"

    id: Mapped[int] = mapped_column(primary_key=True)
    eco: Mapped[str] = mapped_column(String(8), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    moves_uci: Mapped[str] = mapped_column(Text)
    moves_san: Mapped[str] = mapped_column(Text)
    fen_signature: Mapped[str] = mapped_column(String(128), unique=True, index=True)

from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MoveQuality(StrEnum):
    BEST = "best"
    EXCELLENT = "excellent"
    GOOD = "good"
    BOOK = "book"
    INACCURACY = "inaccuracy"
    MISTAKE = "mistake"
    BLUNDER = "blunder"
    BRILLIANT = "brilliant"
    GREAT = "great"
    MISS = "miss"


class MoveAnalysis(Base):
    __tablename__ = "move_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    move_id: Mapped[int] = mapped_column(ForeignKey("moves.id", ondelete="CASCADE"), unique=True)

    depth: Mapped[int]
    eval_cp: Mapped[int | None]
    eval_mate: Mapped[int | None]
    eval_cp_before: Mapped[int | None]
    eval_mate_before: Mapped[int | None]

    cp_loss: Mapped[int | None]
    quality: Mapped[MoveQuality | None] = mapped_column(String(16), index=True)

    best_move_uci: Mapped[str | None] = mapped_column(String(8))
    best_move_san: Mapped[str | None] = mapped_column(String(10))
    pv: Mapped[list[str] | None] = mapped_column(JSONB)
    multipv: Mapped[list[dict] | None] = mapped_column(JSONB)

    tags: Mapped[list[str] | None] = mapped_column(JSONB)

    # Deep re-analysis (run only on critical moves at a higher depth)
    deep_depth: Mapped[int | None]
    deep_eval_cp: Mapped[int | None]
    deep_eval_mate: Mapped[int | None]
    deep_best_uci: Mapped[str | None] = mapped_column(String(8))
    deep_best_san: Mapped[str | None] = mapped_column(String(10))
    deep_pv: Mapped[list[str] | None] = mapped_column(JSONB)

    move = relationship("Move", back_populates="analysis")

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Weakness(Base, TimestampMixin):
    """Aggregated weakness pattern detected across a player's games.

    Examples of `category`:
      - hanging_piece
      - bad_pawn_structure
      - lost_endgame_rook
      - time_trouble
      - falls_for_fried_liver
      - poor_against_d4
    """

    __tablename__ = "weaknesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)

    category: Mapped[str] = mapped_column(String(64), index=True)
    phase: Mapped[str | None] = mapped_column(String(16))  # opening/middlegame/endgame

    occurrences: Mapped[int] = mapped_column(default=0)
    severity: Mapped[float] = mapped_column(default=0.0)

    sample_game_ids: Mapped[list[int] | None] = mapped_column(JSONB)
    details: Mapped[dict | None] = mapped_column(JSONB)

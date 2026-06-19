"""Generate a full-game review: list the player's worst moves with LLM explanations."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, MoveAnalysis, Player
from app.models.analysis import MoveQuality
from app.services.coach.explainer import explain_move


@dataclass
class ReviewItem:
    ply: int
    side_to_move: str
    played: str
    best: str | None
    quality: str | None
    cp_loss: int | None
    explanation: str


async def review_player_mistakes(
    session: AsyncSession,
    game: Game,
    me: Player,
    max_items: int = 5,
) -> list[ReviewItem]:
    my_is_white = game.white_player_id == me.id
    qualities = (MoveQuality.BLUNDER, MoveQuality.MISTAKE)

    bad_moves_q = (
        select(Move.ply)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(Move.game_id == game.id)
        .where(Move.is_white == my_is_white)
        .where(MoveAnalysis.quality.in_(qualities))
        .order_by(MoveAnalysis.cp_loss.desc().nullslast())
        .limit(max_items)
    )
    plies = [r[0] for r in (await session.execute(bad_moves_q)).all()]
    items: list[ReviewItem] = []
    for ply in plies:
        r = await explain_move(session, game, ply)
        if "error" in r:
            continue
        items.append(ReviewItem(
            ply=ply,
            side_to_move=r["side_to_move"],
            played=r["played"],
            best=r.get("best"),
            quality=r.get("quality"),
            cp_loss=r.get("cp_loss"),
            explanation=r["explanation"],
        ))
    return items

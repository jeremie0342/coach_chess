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
    explanation: str            # may be empty when include_llm=False
    pv: list[str] | None = None  # Stockfish principal variation (UCI list)


async def review_player_mistakes(
    session: AsyncSession,
    game: Game,
    me: Player,
    max_items: int = 5,
    include_llm: bool = False,
) -> list[ReviewItem]:
    """List the player's worst moves.

    By default (`include_llm=False`) returns instantly with Stockfish data only.
    Set `include_llm=True` to also fetch LLM explanations (slow — one Ollama
    call per item, ~10-30s each).
    """
    my_is_white = game.white_player_id == me.id
    qualities = (MoveQuality.BLUNDER, MoveQuality.MISTAKE)

    bad_moves_q = (
        select(Move, MoveAnalysis)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(Move.game_id == game.id)
        .where(Move.is_white == my_is_white)
        .where(MoveAnalysis.quality.in_(qualities))
        .order_by(MoveAnalysis.cp_loss.desc().nullslast())
        .limit(max_items)
    )
    rows = (await session.execute(bad_moves_q)).all()
    items: list[ReviewItem] = []
    for move, analysis in rows:
        if include_llm:
            r = await explain_move(session, game, move.ply)
            if "error" in r:
                continue
            items.append(ReviewItem(
                ply=move.ply,
                side_to_move=r["side_to_move"],
                played=r["played"],
                best=r.get("best"),
                quality=r.get("quality"),
                cp_loss=r.get("cp_loss"),
                explanation=r["explanation"],
                pv=(analysis.deep_pv if analysis.deep_pv else analysis.pv),
            ))
        else:
            items.append(ReviewItem(
                ply=move.ply,
                side_to_move="white" if move.is_white else "black",
                played=move.san,
                best=(analysis.deep_best_san or analysis.best_move_san),
                quality=str(analysis.quality) if analysis.quality else None,
                cp_loss=analysis.cp_loss,
                explanation="",
                pv=(analysis.deep_pv if analysis.deep_pv else analysis.pv),
            ))
    return items

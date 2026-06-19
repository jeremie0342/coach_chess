from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Player
from app.services.position_similarity import find_similar

router = APIRouter(prefix="/coach/me", tags=["similarity"])


@router.get("/similar_positions")
async def similar_positions(
    fen: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    max_distance: Annotated[int, Query(ge=0, le=12)] = 4,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    all_players: bool = False,
) -> dict:
    me = None
    if not all_players:
        me = (await session.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalar_one_or_none()
        if not me:
            raise HTTPException(404, "current player not imported")
    matches = await find_similar(
        session, fen, player=me, max_distance=max_distance, limit=limit,
    )
    return {
        "fen": fen,
        "matches": [
            {
                "game_id": m.game_id,
                "ply": m.ply,
                "fen": m.fen,
                "distance": m.distance,
                "quality": m.quality,
                "cp_loss": m.cp_loss,
            }
            for m in matches
        ],
    }

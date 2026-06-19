from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Player
from app.services.lichess_studies import build_pgn_bundle, push_to_study

router = APIRouter(prefix="/lichess", tags=["lichess"])


@router.get(
    "/export_bundle.pgn",
    response_class=PlainTextResponse,
    summary="Multi-game annotated PGN bundle (upload manually to a Lichess study)",
)
async def export_bundle(
    session: Annotated[AsyncSession, Depends(get_session)],
    eco: str | None = None,
    color: str | None = Query(None, regex="^(white|black)$"),
    only_losses: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    include_llm: bool = False,
) -> PlainTextResponse:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    pgn, games = await build_pgn_bundle(
        session, me,
        eco=eco, color=color,
        only_losses=only_losses, limit=limit, include_llm=include_llm,
    )
    return PlainTextResponse(
        pgn,
        media_type="application/x-chess-pgn",
        headers={
            "Content-Disposition": f'attachment; filename="lichess_bundle_{len(games)}.pgn"',
            "X-Games-Included": str(len(games)),
        },
    )


class PushStudyIn(BaseModel):
    study_id: str = Field(..., description="Existing Lichess study ID (create one at https://lichess.org/study)")
    eco: str | None = None
    color: str | None = None
    only_losses: bool = False
    limit: int = Field(20, ge=1, le=32)
    include_llm: bool = False


@router.post("/push_study", summary="Push N analyzed games as chapters into a Lichess study")
async def push_study(
    payload: PushStudyIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    try:
        s = await push_to_study(
            session, me, study_id=payload.study_id,
            eco=payload.eco, color=payload.color,
            only_losses=payload.only_losses,
            limit=payload.limit, include_llm=payload.include_llm,
        )
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {
        "study_id": payload.study_id,
        "chapters_pushed": s.chapters_pushed,
        "chapters_failed": s.chapters_failed,
        "bytes_sent": s.bytes_sent,
        "errors": s.errors[:5],
    }

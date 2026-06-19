from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import RepertoireNode
from app.models.repertoire import RepertoireColor
from app.services.trainer.session import (
    compute_stats,
    grade_answer,
    pick_next_due,
)

router = APIRouter(prefix="/trainer", tags=["trainer"])


class AnswerIn(BaseModel):
    node_id: int
    move: str           # SAN or UCI
    time_ms: int | None = None


@router.get("/next")
async def next_card(
    session: Annotated[AsyncSession, Depends(get_session)],
    color: RepertoireColor | None = None,
) -> dict:
    card = await pick_next_due(session, color=color)
    if not card:
        return {"has_card": False}
    n = card.node
    return {
        "has_card": True,
        "is_new": card.is_new,
        "due_now": card.due_now,
        "node": {
            "id": n.id,
            "color": str(n.color),
            "fen": n.fen,
            "label": n.label,
            "notes": n.notes,
        },
    }


@router.post("/answer")
async def answer(
    payload: AnswerIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    node = (await session.execute(
        select(RepertoireNode).where(RepertoireNode.id == payload.node_id)
    )).scalar_one_or_none()
    if not node:
        raise HTTPException(404, "node not found")
    result = await grade_answer(session, node, payload.move, time_ms=payload.time_ms)
    return {
        "node_id": result.node_id,
        "correct": result.correct,
        "grade": result.grade,
        "expected_san": result.expected_san,
        "expected_uci": result.expected_uci,
        "user_uci": result.user_uci,
        "alternates": result.alternates,
        "new_interval_days": result.new_interval_days,
        "new_due_at": result.new_due_at.isoformat(),
    }


@router.get("/stats")
async def stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    color: RepertoireColor | None = None,
) -> dict:
    s = await compute_stats(session, color=color)
    return {
        "total_nodes": s.total_nodes,
        "new_nodes": s.new_nodes,
        "learning_nodes": s.learning_nodes,
        "due_today": s.due_today,
        "next_due_at": s.next_due_at.isoformat() if s.next_due_at else None,
    }

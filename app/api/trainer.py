from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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
from app.services.llm.ollama import ChatMessage, OllamaClient

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

    # Identify the opening name if any matches the position
    opening_name = None
    eco = None
    try:
        from app.services.openings.theory import match_position
        m = await match_position(session, n.fen)
        if m:
            opening_name = m.name
            eco = m.eco
    except Exception:
        pass

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
            "plan": n.plan,
            "traps": n.traps,
            # GM context if previously annotated via Lichess explorer
            "gm_total_games": n.gm_total_games,
            "gm_my_move_score": n.gm_my_move_score,
            "gm_my_move_share": n.gm_my_move_share,
            "gm_moves": (n.gm_moves or [])[:5],
            "opening_name": opening_name,
            "eco": eco,
            # SR state
            "sr_repetitions": n.sr_repetitions,
            "sr_interval_days": n.sr_interval_days,
            "sr_ease": round(n.sr_ease, 2),
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
        "expected_source": result.expected_source,
        "expected_score": result.expected_score,
        "user_uci": result.user_uci,
        "alternates": result.alternates,
        "your_usual_san": result.your_usual_san,
        "your_usual_uci": result.your_usual_uci,
        "plays_usual": result.plays_usual,
        "is_best_your_usual": result.is_best_your_usual,
        "new_interval_days": result.new_interval_days,
        "new_due_at": result.new_due_at.isoformat(),
    }


@router.post("/{node_id}/explain/stream", summary="LLM coach commentary on a repertoire node (streamed)")
async def explain_node_stream(
    node_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StreamingResponse:
    node = (await session.execute(
        select(RepertoireNode).where(RepertoireNode.id == node_id)
    )).scalar_one_or_none()
    if not node:
        raise HTTPException(404, "node not found")

    opening_name = None
    eco = None
    try:
        from app.services.openings.theory import match_position
        m = await match_position(session, node.fen)
        if m:
            opening_name = m.name
            eco = m.eco
    except Exception:
        pass

    color_label = "Blancs" if str(node.color).endswith("white") else "Noirs"
    gm_block = ""
    if node.gm_total_games and node.gm_moves:
        lines = []
        for m in (node.gm_moves or [])[:5]:
            lines.append(
                f"  {m.get('san','?')} : {m.get('games',0)} parties, "
                f"score_white={m.get('score_white','?')}"
            )
        gm_block = "Distribution GM (Lichess masters DB) :\n" + "\n".join(lines)

    system = (
        "Tu es un coach d'échecs francophone, pédagogue. L'utilisateur est un "
        "joueur amateur ~450 ELO. Explique-lui ce node de son répertoire :\n"
        "- ce que représente cette position dans le voyage d'ouverture\n"
        "- pourquoi son coup habituel a du sens (ou pas) selon les GMs\n"
        "- l'idée stratégique de la suite (plan, structure, but)\n"
        "Reste fluide, 3-5 phrases, sans listes ni jargon excessif."
    )

    user_parts = [
        f"Position : {node.fen}",
        f"Trait aux {color_label} (l'utilisateur joue cette couleur)",
        f"Ouverture identifiée : {opening_name or '—'} ({eco or '—'})",
        f"Coup habituel de l'utilisateur : {node.move_san or '—'} ({node.move_uci or '—'})",
    ]
    if node.notes:
        user_parts.append(f"Stats personnelles :\n{node.notes}")
    if gm_block:
        user_parts.append(gm_block)
    if node.gm_my_move_share is not None:
        user_parts.append(
            f"Part GM du coup utilisateur : {node.gm_my_move_share:.2%}, "
            f"score : {node.gm_my_move_score:.2f}" if node.gm_my_move_score else
            f"Part GM du coup utilisateur : {node.gm_my_move_share:.2%}"
        )
    if node.plan:
        user_parts.append(f"Plan noté : {node.plan}")

    user_msg = "\n\n".join(user_parts) + "\n\nExplique."

    async def gen():
        async with OllamaClient() as client:
            async for chunk in client.chat_stream(
                [ChatMessage(role="system", content=system),
                 ChatMessage(role="user", content=user_msg)],
            ):
                yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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

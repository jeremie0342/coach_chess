"""LLM-generated short coach message for a daily plan."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyPlan, DailyPlanItem
from app.services.llm.ollama import ChatMessage, OllamaClient

logger = logging.getLogger(__name__)


COACH_SYSTEM = """Tu es un coach d'échecs francophone, motivant et concret. Tu rédiges un court message d'introduction (3-4 phrases max) pour la session du jour de ton joueur.

Le message doit :
- Saluer brièvement et nommer la priorité du jour (la faiblesse principale)
- Résumer en une phrase ce que la session va couvrir (sans énumérer en détail — il verra la liste juste en dessous)
- Finir sur une note d'encouragement courte, sans cliché

Pas de listes. Pas de markdown. Ton direct."""


async def generate_message(session: AsyncSession, plan: DailyPlan) -> str | None:
    items = list((await session.execute(
        select(DailyPlanItem).where(DailyPlanItem.plan_id == plan.id)
        .order_by(DailyPlanItem.order_index)
    )).scalars())

    lines = [
        f"Joueur: {plan.player_id} (élo ~450, vise 2000)",
        f"Faiblesse principale aujourd'hui: {plan.weakness_focus or 'aucune dominante'}",
        f"Budget temps cible: {plan.target_minutes} min",
        "",
        "Items du plan:",
    ]
    for it in items:
        lines.append(f"  - {it.kind}: {it.title}  ({it.estimated_minutes} min) — {it.rationale}")

    prompt = "\n".join(lines) + "\n\nRédige ton message d'intro."
    try:
        async with OllamaClient() as client:
            msg = await client.chat(
                [
                    ChatMessage(role="system", content=COACH_SYSTEM),
                    ChatMessage(role="user", content=prompt),
                ],
                temperature=0.5,
                num_predict=180,
            )
        return msg
    except Exception as e:
        logger.warning("Lesson plan LLM message failed: %r (%s)", e, type(e).__name__)
        return None

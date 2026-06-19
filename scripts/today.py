"""Show today's auto-composed training plan.

Usage:
    uv run python scripts/today.py
    uv run python scripts/today.py --minutes 45 --regenerate
    uv run python scripts/today.py --no-llm
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import DailyPlanItem, Player
from app.services.coach.lesson_message import generate_message
from app.services.coach.lesson_plan import compose_daily_plan


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        me = (await session.execute(
            select(Player).where(Player.is_me.is_(True))
        )).scalar_one_or_none()
        if not me:
            print("No 'is_me' player. Run an import first.")
            return 1
        plan = await compose_daily_plan(
            session, me,
            target_minutes=args.minutes,
            force=args.regenerate,
        )
        if not args.no_llm and (args.regenerate or not plan.coach_message):
            msg = await generate_message(session, plan)
            if msg:
                plan.coach_message = msg
                await session.commit()

        items = list((await session.execute(
            select(DailyPlanItem)
            .where(DailyPlanItem.plan_id == plan.id)
            .order_by(DailyPlanItem.order_index)
        )).scalars())

    print(f"\n=== Today {plan.plan_date} — {me.chesscom_username} ===")
    print(f"Budget: {plan.target_minutes} min  |  Focus: {plan.weakness_focus or '-'}")
    if plan.coach_message:
        print(f"\n>> Coach:\n{plan.coach_message}\n")
    print("Plan:")
    total = 0
    for it in items:
        done = f"({it.completed_count}/{it.target_count})" if it.target_count else ""
        print(f"\n  [{it.order_index + 1}] {it.kind}  {done}  ~{it.estimated_minutes} min")
        print(f"      {it.title}")
        print(f"      filters: {it.filters or {}}")
        if it.rationale:
            print(f"      why: {it.rationale}")
        total += it.estimated_minutes
    print(f"\nEstimated total: {total} min")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--minutes", type=int, default=30)
    p.add_argument("--regenerate", action="store_true")
    p.add_argument("--no-llm", action="store_true", help="Skip coach LLM message")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

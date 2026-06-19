"""Lesson plan compose: end-to-end with real Weakness rows."""
from __future__ import annotations

import pytest

from app.models import DailyPlan, DailyPlanItem, Weakness
from app.services.coach.lesson_plan import compose_daily_plan
from tests.factories import make_player


pytestmark = pytest.mark.db


async def test_compose_picks_top_weakness_as_focus(db_session) -> None:
    me = await make_player(db_session, "alice")
    db_session.add_all([
        Weakness(player_id=me.id, category="missed_tactic",
                 phase=None, occurrences=80, severity=0.9),
        Weakness(player_id=me.id, category="time_trouble",
                 phase=None, occurrences=10, severity=0.3),
    ])
    await db_session.commit()
    plan = await compose_daily_plan(db_session, me, target_minutes=30)
    assert plan.weakness_focus == "missed_tactic"


async def test_compose_is_idempotent_per_day(db_session) -> None:
    me = await make_player(db_session, "alice")
    plan1 = await compose_daily_plan(db_session, me, target_minutes=30)
    plan2 = await compose_daily_plan(db_session, me, target_minutes=30)
    assert plan1.id == plan2.id


async def test_compose_force_replaces_plan(db_session) -> None:
    me = await make_player(db_session, "alice")
    plan1 = await compose_daily_plan(db_session, me, target_minutes=30)
    plan2 = await compose_daily_plan(db_session, me, target_minutes=45, force=True)
    assert plan2.id != plan1.id
    assert plan2.target_minutes == 45


async def test_compose_emits_no_items_when_no_data(db_session) -> None:
    """Player with no weaknesses, no due cards, no exercises."""
    me = await make_player(db_session, "alice")
    plan = await compose_daily_plan(db_session, me, target_minutes=30)
    from sqlalchemy import select
    items = list((await db_session.execute(
        select(DailyPlanItem).where(DailyPlanItem.plan_id == plan.id)
    )).scalars())
    # No data → nothing to drill (allowed; the LLM message would still say so)
    assert items == []


async def test_compose_routes_missed_fork_to_fork_puzzles(db_session) -> None:
    me = await make_player(db_session, "alice")
    db_session.add(Weakness(
        player_id=me.id, category="missed_fork", phase=None,
        occurrences=20, severity=0.9,
    ))
    await db_session.commit()
    plan = await compose_daily_plan(db_session, me, target_minutes=30)
    from sqlalchemy import select
    items = list((await db_session.execute(
        select(DailyPlanItem).where(DailyPlanItem.plan_id == plan.id)
    )).scalars())
    fork_items = [i for i in items if (i.filters or {}).get("theme") == "fork"]
    assert fork_items, "expected at least one fork-themed puzzle block"

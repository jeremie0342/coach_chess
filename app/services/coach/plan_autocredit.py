"""Auto-credit daily plan items from objective signals.

Today we only auto-credit COACH_NOTE items whose `filters.time_controls`
contains one of the chess.com `time_control` strings (e.g. "900+10" for 15+10,
"1800" for 30+0). For each unfinished item, we count distinct games played by
the current user since the plan was created (or, fallback: since plan_date
midnight UTC) matching any of the configured time controls. If that count is
higher than the persisted completed_count, we bump it.

Idempotent: re-running on the same data is a no-op.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyPlan, DailyPlanItem, Exercise, Game, OpeningProgress, Player
from app.models.daily_plan import DailyItemKind
from app.models.exercise import ExerciseKind


@dataclass
class CreditReport:
    items_updated: int
    items_completed: int


def _plan_window_start(plan: DailyPlan) -> datetime:
    """Earliest moment a game counts toward this plan."""
    # plan_date is a date (no tz). Anchor at midnight UTC.
    anchor = datetime.combine(plan.plan_date, time.min).replace(tzinfo=timezone.utc)
    # Or use plan.created_at if it's already after midnight (safer for back-dated plans).
    created = plan.created_at
    if created is not None and created > anchor:
        return anchor  # we still want all games of that day
    return anchor


async def auto_credit_from_games(
    session: AsyncSession,
    plan: DailyPlan,
    me: Player,
) -> CreditReport:
    """Bump completed_count of plan items matching played time_controls.

    Returns counts of items touched. Caller must commit the session.
    """
    items = list((await session.execute(
        select(DailyPlanItem)
        .where(DailyPlanItem.plan_id == plan.id)
        .where(DailyPlanItem.completed_at.is_(None))
    )).scalars())

    if not items:
        return CreditReport(0, 0)

    # --- Pass 1: time_controls filter -----------------------------------
    wanted_per_item: dict[int, list[str]] = {}
    all_tcs: set[str] = set()
    lab_review_items: list = []
    for it in items:
        f = it.filters or {}
        tcs = f.get("time_controls")
        if tcs:
            if isinstance(tcs, str):
                tcs = [tcs]
            if tcs:
                wanted_per_item[it.id] = list(tcs)
                all_tcs.update(tcs)
        if f.get("needs_lab_review"):
            lab_review_items.append(it)

    since = _plan_window_start(plan)
    count_by_tc: dict[str, int] = {}
    if all_tcs:
        rows = list((await session.execute(
            select(Game.id, Game.time_control, Game.played_at)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.played_at.is_not(None))
            .where(Game.played_at >= since)
            .where(Game.time_control.in_(all_tcs))
        )).all())
        seen_games: set[int] = set()
        for gid, tc, _ in rows:
            if gid in seen_games:
                continue
            seen_games.add(gid)
            count_by_tc[tc] = count_by_tc.get(tc, 0) + 1

    # --- Pass 2: lab review filter --------------------------------------
    lab_reviewed_today = 0
    if lab_review_items:
        lab_reviewed_today = (await session.execute(
            select(func.count(Game.id))
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.lab_reviewed_at.is_not(None))
            .where(Game.lab_reviewed_at >= since)
        )).scalar_one() or 0

    # --- Pass 3: puzzles solved today --------------------------------
    # Strategy: count puzzles whose theme_tags intersect the item's coach-
    # recommended themes. If the item has no `themes` filter, fall back to
    # counting by exercise kind. This handles the case where a "fork" puzzle
    # happens to have kind=endgame (it should still credit puzzle_focused).
    kind_to_exercise_kind: dict[str, list[str]] = {
        str(DailyItemKind.PUZZLE_FOCUSED): [
            str(ExerciseKind.TACTIC),
            str(ExerciseKind.CALCULATION),
            str(ExerciseKind.POSITIONAL),
        ],
        str(DailyItemKind.BLUNDER_REVIEW): [str(ExerciseKind.TACTIC)],
        str(DailyItemKind.ENDGAME_PRACTICE): [str(ExerciseKind.ENDGAME)],
    }
    puzzle_items = [it for it in items if str(it.kind) in kind_to_exercise_kind]

    # Pre-compute "solved today" counts per item using theme intersection
    # when the plan item has coach-recommended themes.
    from sqlalchemy import or_ as sa_or
    solved_per_item: dict[int, int] = {}
    for it in puzzle_items:
        filters = it.filters or {}
        themes = filters.get("themes")
        if isinstance(themes, str):
            themes = [themes]
        # endgame_practice should always restrict to endgame kind, even if
        # themes aren't set (preserves prior behavior).
        if str(it.kind) == str(DailyItemKind.ENDGAME_PRACTICE) and not themes:
            n = (await session.execute(
                select(func.count(Exercise.id))
                .where(Exercise.last_solved_at.is_not(None))
                .where(Exercise.last_solved_at >= since)
                .where(Exercise.kind == ExerciseKind.ENDGAME)
            )).scalar_one() or 0
            solved_per_item[it.id] = int(n)
            continue

        # blunder_review: from my own games
        if str(it.kind) == str(DailyItemKind.BLUNDER_REVIEW):
            n = (await session.execute(
                select(func.count(Exercise.id))
                .where(Exercise.last_solved_at.is_not(None))
                .where(Exercise.last_solved_at >= since)
                .where(Exercise.source_kind == "blunder")
            )).scalar_one() or 0
            solved_per_item[it.id] = int(n)
            continue

        # puzzle_focused with themes: theme-intersection counting (any-of)
        if themes:
            theme_predicates = [Exercise.theme_tags.op("?")(t) for t in themes]
            n = (await session.execute(
                select(func.count(Exercise.id))
                .where(Exercise.last_solved_at.is_not(None))
                .where(Exercise.last_solved_at >= since)
                .where(sa_or(*theme_predicates))
            )).scalar_one() or 0
            solved_per_item[it.id] = int(n)
            continue

        # puzzle_focused without themes: fall back to kind-based count
        ex_kinds = kind_to_exercise_kind.get(str(it.kind), [])
        if ex_kinds:
            n = (await session.execute(
                select(func.count(Exercise.id))
                .where(Exercise.last_solved_at.is_not(None))
                .where(Exercise.last_solved_at >= since)
                .where(Exercise.kind.in_(ex_kinds))
            )).scalar_one() or 0
            solved_per_item[it.id] = int(n)

    # --- Apply ----------------------------------------------------------
    now = datetime.now(timezone.utc)
    items_updated = 0
    items_completed = 0

    for it in items:
        new_count: int | None = None

        tc_wanted = wanted_per_item.get(it.id)
        if tc_wanted:
            matched = sum(count_by_tc.get(tc, 0) for tc in tc_wanted)
            new_count = min(matched, it.target_count)

        if (it.filters or {}).get("needs_lab_review"):
            new_count = min(int(lab_reviewed_today), it.target_count)

        # OPENING_STUDY: 1 if the linked opening was drilled perfectly today.
        if str(it.kind) == str(DailyItemKind.OPENING_STUDY):
            opening_key = (it.filters or {}).get("opening_key")
            if opening_key:
                today = datetime.now(timezone.utc).date()
                prog = (await session.execute(
                    select(OpeningProgress)
                    .where(OpeningProgress.player_id == me.id)
                    .where(OpeningProgress.opening_key == opening_key)
                )).scalar_one_or_none()
                if prog and prog.last_perfect_date == today:
                    new_count = it.target_count  # mark complete

        # Puzzles — pre-computed per-item count (theme-aware).
        if it.id in solved_per_item:
            solved = solved_per_item[it.id]
            candidate = min(solved, it.target_count)
            if new_count is None or candidate > new_count:
                new_count = candidate

        if new_count is None or new_count <= (it.completed_count or 0):
            continue

        it.completed_count = new_count
        items_updated += 1
        if new_count >= it.target_count and it.completed_at is None:
            it.completed_at = now
            items_completed += 1

    return CreditReport(items_updated, items_completed)

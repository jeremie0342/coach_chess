"""Daily opening mastery rotation.

The user maintains 2 active opening slots:
  - 1 white opening (e.g. London System)
  - 1 black opening (e.g. King's Indian Defense - Mar del Plata)

Mechanics:
  * Each day, the user is expected to play through the active opening of each
    color in the opening trainer without any wrong move.
  * Successful perfect-run on day D increments streak_days (if last_perfect_date
    is yesterday) or sets it to 1 (if older).
  * A wrong move during the day's attempt resets streak_days to 0 (the same
    day's perfect run still counts later).
  * At MASTERY_STREAK (7) consecutive perfect days, the variant is MASTERED
    and we rotate in the next unmastered variant of the same color.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OpeningProgress, OpeningProgressStatus, Player
from app.models.opening_progress import MASTERY_STREAK
from app.services.opening_trainer import LIBRARY


# Map ECO/name signals from the personality-based opening_recommendation
# service back to our trainer library keys. The recommender returns openings
# by NAME (e.g. "King's Gambit", "King's Indian Defense") and ECO codes; we
# fuzzy-match on base_name first, then on a curated alias table.
_BASE_NAME_ALIASES: dict[str, list[str]] = {
    # canonical trainer base_name -> list of substring patterns from the
    # opening_recommendation service that should map to it
    "King's Gambit": ["king's gambit", "kings gambit"],
    "King's Indian Defense": ["king's indian", "kings indian", "kid"],
    "Sicilian Najdorf": ["sicilian najdorf", "najdorf"],
    "Modern Benoni": ["modern benoni", "benoni"],
    "London System": ["london system"],
    "Italian Game": ["italian game", "giuoco piano"],
    "Queen's Gambit": ["queen's gambit", "queens gambit"],
    "French Defense": ["french defense", "french"],
}


# Fallback "always available" ordering per color, used only if the coach's
# personality-driven recommender returned nothing for that color. Solid
# starters chosen for low-rated players.
_FALLBACK_ORDER: dict[str, list[str]] = {
    "white": [
        "italian_game",
        "london_system",
        "queens_gambit",
        "kings_gambit_declined",
        "kings_gambit_accepted",
    ],
    "black": [
        "french_defense",
        "kid_mar_del_plata",
        "kid_saemisch",
        "sicilian_najdorf_english",
        "sicilian_najdorf_bg5",
        "modern_benoni_classical",
    ],
}


def _match_trainer_keys_for_recommendation(rec_name: str) -> list[str]:
    """Return trainer LIBRARY keys whose base_name matches the recommended name."""
    name_lower = rec_name.lower()
    for canonical, patterns in _BASE_NAME_ALIASES.items():
        if any(p in name_lower for p in patterns):
            # Return all variants whose base_name matches this canonical name.
            return [k for k, op in LIBRARY.items() if op.base_name == canonical]
    return []


async def _preferred_order_for_color(
    session: AsyncSession,
    player: Player,
    color: str,
) -> list[str]:
    """Compute the ordered list of trainer keys for the user, by color.

    Priority (highest -> lowest):
      1. The user's own PlayerRepertoireEntry list, in their chosen order.
         This is the source of truth — what the user explicitly wants to study.
      2. Personality-based opening recommender (legacy fallback).
      3. Hard-coded fallback (curated solid starters) — last resort.
    """
    keys_ordered: list[str] = []

    # 1. User's curated repertoire (highest priority)
    try:
        from app.models import PlayerRepertoireEntry
        rep_keys = list((await session.execute(
            select(PlayerRepertoireEntry.opening_key)
            .where(PlayerRepertoireEntry.player_id == player.id)
            .where(PlayerRepertoireEntry.user_color == color)
            .order_by(PlayerRepertoireEntry.position, PlayerRepertoireEntry.id)
        )).scalars())
        for k in rep_keys:
            if k in LIBRARY and k not in keys_ordered:
                keys_ordered.append(k)
    except Exception:
        pass

    # 2. Personality-based recommender
    try:
        from app.services.opening_recommendation import recommend as recommend_openings
        recs = await recommend_openings(session, player)
        for r in recs:
            if r.color != color:
                continue
            for key in _match_trainer_keys_for_recommendation(r.name):
                if key not in keys_ordered:
                    keys_ordered.append(key)
    except Exception:
        pass

    # 3. Hard-coded fallback
    for key in _FALLBACK_ORDER.get(color, []):
        if key not in keys_ordered:
            keys_ordered.append(key)
    return keys_ordered


async def get_or_seed_active(
    session: AsyncSession,
    player: Player,
    color: Literal["white", "black"],
) -> OpeningProgress | None:
    """Return the active opening_progress row for the given color slot.

    Bootstraps the first preferred variant if no row exists yet. Skips
    variants already mastered.
    """
    # Existing active variant?
    # If the user has a personal repertoire, prefer an ACTIVE row that is part
    # of it. Orphan ACTIVE rows (e.g. a previously-recommended opening the user
    # later removed from their repertoire) are bypassed so the rotation always
    # tracks the user's current intent.
    from app.models import PlayerRepertoireEntry
    rep_keys_for_color = set((await session.execute(
        select(PlayerRepertoireEntry.opening_key)
        .where(PlayerRepertoireEntry.player_id == player.id)
        .where(PlayerRepertoireEntry.user_color == color)
    )).scalars())

    active_rows = list((await session.execute(
        select(OpeningProgress)
        .where(OpeningProgress.player_id == player.id)
        .where(OpeningProgress.user_color == color)
        .where(OpeningProgress.status == OpeningProgressStatus.ACTIVE)
    )).scalars())

    if active_rows:
        if rep_keys_for_color:
            in_rep = [r for r in active_rows if r.opening_key in rep_keys_for_color]
            if in_rep:
                return in_rep[0]
            # All active rows are orphan (not in the user's curated repertoire).
            # Fall through to seed a new ACTIVE from the repertoire.
        else:
            return active_rows[0]

    # Find the next un-mastered variant for this color, in preferred order
    # derived from the coach's personality-driven opening recommendations.
    mastered_keys = set((await session.execute(
        select(OpeningProgress.opening_key)
        .where(OpeningProgress.player_id == player.id)
        .where(OpeningProgress.status == OpeningProgressStatus.MASTERED)
    )).scalars())

    preferred = await _preferred_order_for_color(session, player, color)
    for key in preferred:
        if key in mastered_keys:
            continue
        op = LIBRARY.get(key)
        if op is None or op.user_color != color:
            continue
        # Create new active row
        row = OpeningProgress(
            player_id=player.id,
            opening_key=op.key,
            base_name=op.base_name,
            user_color=color,
            status=OpeningProgressStatus.ACTIVE,
        )
        session.add(row)
        await session.flush()
        return row

    # All preferred variants mastered — fallback to any non-mastered variant.
    for op in LIBRARY.values():
        if op.user_color != color:
            continue
        if op.key in mastered_keys:
            continue
        row = OpeningProgress(
            player_id=player.id,
            opening_key=op.key,
            base_name=op.base_name,
            user_color=color,
            status=OpeningProgressStatus.ACTIVE,
        )
        session.add(row)
        await session.flush()
        return row
    return None


async def record_attempt(
    session: AsyncSession,
    player: Player,
    opening_key: str,
    *,
    is_perfect: bool,
    today: date | None = None,
) -> OpeningProgress | None:
    """Record an opening-trainer attempt outcome and update streak/status.

    Args:
      is_perfect: True if the user completed the variant with 0 wrong moves
                  in this session.

    Returns the updated OpeningProgress (or None if opening not found).
    """
    today = today or datetime.now(timezone.utc).date()

    row = (await session.execute(
        select(OpeningProgress)
        .where(OpeningProgress.player_id == player.id)
        .where(OpeningProgress.opening_key == opening_key)
        .limit(1)
    )).scalar_one_or_none()

    if row is None:
        op = LIBRARY.get(opening_key)
        if op is None:
            return None
        row = OpeningProgress(
            player_id=player.id,
            opening_key=opening_key,
            base_name=op.base_name,
            user_color=op.user_color,
        )
        session.add(row)
        await session.flush()

    row.attempts = (row.attempts or 0) + 1

    if not is_perfect:
        # Failed run today resets the streak.
        row.streak_days = 0
        await session.flush()
        return row

    # Perfect run.
    row.perfect_runs = (row.perfect_runs or 0) + 1
    if row.last_perfect_date == today:
        # Already counted today — no extra streak bump but keep accumulating.
        await session.flush()
        return row

    # Streak logic: only consecutive days count.
    if row.last_perfect_date is not None and (today - row.last_perfect_date).days == 1:
        row.streak_days = (row.streak_days or 0) + 1
    else:
        row.streak_days = 1
    row.last_perfect_date = today
    if row.streak_days > (row.best_streak or 0):
        row.best_streak = row.streak_days

    if row.streak_days >= MASTERY_STREAK and row.status == OpeningProgressStatus.ACTIVE:
        row.status = OpeningProgressStatus.MASTERED
        row.mastered_at = datetime.now(timezone.utc)
        # The next /coach/me/today call will pick up the next preferred variant
        # via get_or_seed_active when planning the day.

    await session.flush()
    return row


async def list_progress(
    session: AsyncSession, player: Player
) -> list[OpeningProgress]:
    rows = list((await session.execute(
        select(OpeningProgress)
        .where(OpeningProgress.player_id == player.id)
        .order_by(OpeningProgress.user_color, OpeningProgress.status.desc())
    )).scalars())
    return rows

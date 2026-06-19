"""Weakness engine: no duplicate rows per (player, category, phase)."""
from __future__ import annotations

import pytest
from sqlalchemy import and_, func, select

from app.models import Weakness
from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding
from app.services.weakness_engine import refresh_player_weaknesses
from tests.factories import make_player


pytestmark = pytest.mark.db


class _MultiEmittingDetector(Detector):
    """Emits 3 findings with same (category, phase) — used to bait the upsert bug."""
    category = "test_duplicate"
    requires_analysis = False

    async def detect(self, ctx: DetectorContext):
        for i in range(3):
            yield WeaknessFinding(
                category=self.category,
                phase="opening",
                occurrences=10 + i,
                severity=0.5,
                sample_game_ids=[i],
                details={"i": i},
            )


async def test_no_duplicate_weakness_rows_when_detector_emits_multiple(db_session) -> None:
    me = await make_player(db_session, "alice")
    await refresh_player_weaknesses(
        db_session, me, detectors=[_MultiEmittingDetector()], prune_missing=False,
    )
    n = (await db_session.execute(
        select(func.count(Weakness.id)).where(
            and_(Weakness.player_id == me.id, Weakness.category == "test_duplicate")
        )
    )).scalar_one()
    assert n == 1, "exactly one row per (player_id, category, phase)"


async def test_rerunning_refresh_overwrites_existing_row(db_session) -> None:
    me = await make_player(db_session, "alice")
    det = _MultiEmittingDetector()
    await refresh_player_weaknesses(db_session, me, detectors=[det], prune_missing=False)
    await refresh_player_weaknesses(db_session, me, detectors=[det], prune_missing=False)
    n = (await db_session.execute(
        select(func.count(Weakness.id)).where(Weakness.player_id == me.id)
    )).scalar_one()
    assert n == 1


class _NoFindingDetector(Detector):
    category = "ghost"
    async def detect(self, ctx: DetectorContext):
        return
        yield  # unreachable; required for it to be an async generator


async def test_prune_missing_removes_stale_rows(db_session) -> None:
    me = await make_player(db_session, "alice")
    # First populate one Weakness
    await refresh_player_weaknesses(
        db_session, me, detectors=[_MultiEmittingDetector()], prune_missing=False,
    )
    # Now run with a detector that emits NOTHING + prune_missing=True
    await refresh_player_weaknesses(
        db_session, me, detectors=[_NoFindingDetector()], prune_missing=True,
    )
    n = (await db_session.execute(
        select(func.count(Weakness.id)).where(Weakness.player_id == me.id)
    )).scalar_one()
    assert n == 0

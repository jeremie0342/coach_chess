"""Run all detectors for a player and upsert Weakness rows.

One row per (player_id, category[, phase]) — re-runs overwrite occurrences,
severity, sample_game_ids and details.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player, Weakness
from app.services.detectors import DEFAULT_DETECTORS
from app.services.detectors.base import Detector, DetectorContext, WeaknessFinding

logger = logging.getLogger(__name__)


@dataclass
class EngineReport:
    detectors_run: int = 0
    findings_emitted: int = 0
    rows_upserted: int = 0
    findings: list[WeaknessFinding] | None = None

    def __post_init__(self) -> None:
        if self.findings is None:
            self.findings = []


async def refresh_player_weaknesses(
    session: AsyncSession,
    player: Player,
    detectors: list[Detector] | None = None,
    prune_missing: bool = True,
) -> EngineReport:
    detectors = detectors or DEFAULT_DETECTORS
    report = EngineReport()
    ctx = DetectorContext(session=session, player=player)

    seen_keys: set[tuple[str, str | None]] = set()

    for det in detectors:
        report.detectors_run += 1
        async for finding in det.detect(ctx):
            report.findings.append(finding)
            report.findings_emitted += 1
            seen_keys.add((finding.category, finding.phase))
            await _upsert_finding(session, player.id, finding)
            report.rows_upserted += 1

    if prune_missing:
        # Remove old Weakness rows that no detector emitted this run
        existing = list((await session.execute(
            select(Weakness).where(Weakness.player_id == player.id)
        )).scalars())
        for w in existing:
            if (w.category, w.phase) not in seen_keys:
                await session.delete(w)

    await session.commit()
    logger.info(
        "refresh_player_weaknesses player=%s detectors=%d findings=%d",
        player.chesscom_username, report.detectors_run, report.findings_emitted,
    )
    return report


async def _upsert_finding(
    session: AsyncSession, player_id: int, finding: WeaknessFinding
) -> None:
    """Find-or-update one Weakness row per (player_id, category, phase).

    If legacy duplicate rows exist (older bug), we keep the first and prune
    the rest in-place. We flush after each upsert so subsequent SELECTs in
    the same transaction see the row.
    """
    q = select(Weakness).where(
        and_(
            Weakness.player_id == player_id,
            Weakness.category == finding.category,
            (Weakness.phase == finding.phase) if finding.phase is not None else Weakness.phase.is_(None),
        )
    )
    rows = list((await session.execute(q)).scalars())
    if rows:
        head, *dupes = rows
        head.occurrences = finding.occurrences
        head.severity = finding.severity
        head.sample_game_ids = finding.sample_game_ids
        head.details = finding.details
        for dup in dupes:
            await session.delete(dup)
        await session.flush()
        return
    session.add(Weakness(
        player_id=player_id,
        category=finding.category,
        phase=finding.phase,
        occurrences=finding.occurrences,
        severity=finding.severity,
        sample_game_ids=finding.sample_game_ids,
        details=finding.details,
    ))
    await session.flush()

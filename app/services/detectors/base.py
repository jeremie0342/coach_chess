"""Detector contract.

A Detector inspects the games of a single player and yields zero or more
WeaknessFinding objects. The orchestrator (weakness_engine) is responsible
for persisting them (upsert one row per (player_id, category)).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player


@dataclass
class WeaknessFinding:
    category: str
    phase: str | None = None
    occurrences: int = 0
    severity: float = 0.0  # 0..1 — how serious / how much it costs you
    sample_game_ids: list[int] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectorContext:
    session: AsyncSession
    player: Player
    # Hard cap on game IDs we collect as examples — DB stays light
    max_samples: int = 20


class Detector(ABC):
    """Subclasses override `category` (and optionally `phase`) and `detect()`."""

    category: str = ""
    requires_analysis: bool = False

    @abstractmethod
    async def detect(self, ctx: DetectorContext) -> AsyncIterator[WeaknessFinding]:
        """Yield zero or more findings for this player."""
        raise NotImplementedError
        # Make this an async-gen even when empty:
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]

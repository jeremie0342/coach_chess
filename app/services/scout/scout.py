"""Orchestrator: full opponent scouting report.

Steps:
  1. Pull opponent's last N months / max M games from Chess.com.
  2. Compute out-of-book + deepest_opening for those games.
  3. Run weakness detectors on this opponent (they're generic — they work
     for any Player, not just is_me).
  4. Compute opening profile (first moves, top openings per color).
  5. Optionally synthesize a battle plan via the LLM.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field  # noqa: F401

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player, Weakness
from app.services.import_orchestrator import import_recent_months
from app.services.llm.ollama import ChatMessage, OllamaClient
from app.services.openings.out_of_book import compute_out_of_book_for_all_my_games
from app.services.scout.opening_stats import (
    OpponentOpeningReport,
    compute_opening_report,
)
from app.services.scout.enrichment import (
    LearningOpeningProbe,
    OpponentProfile,
    PhaseQualityStats,
    RepertoireBranch,
    compute_opponent_profile,
    compute_phase_quality,
    compute_vs_learning_openings,
    compute_vs_my_repertoire,
    generate_deterministic_plan,
)
from app.services.weakness_engine import refresh_player_weaknesses

logger = logging.getLogger(__name__)


@dataclass
class ScoutReport:
    opponent_username: str
    games_imported: int
    games_skipped: int
    opening_report: OpponentOpeningReport
    weaknesses: list[dict]
    profile: OpponentProfile | None = None
    phase_quality: list[PhaseQualityStats] = field(default_factory=list)
    vs_my_repertoire: list[RepertoireBranch] = field(default_factory=list)
    vs_learning_openings: list[LearningOpeningProbe] = field(default_factory=list)
    structured_plan: str | None = None
    battle_plan: str | None = None
    elapsed_s: float = 0.0


async def _get_or_create_opponent(session: AsyncSession, username: str) -> Player:
    username = username.lower()
    me = (await session.execute(
        select(Player).where(Player.chesscom_username == username)
    )).scalar_one_or_none()
    if me:
        return me
    p = Player(chesscom_username=username, display_name=username, is_me=False)
    session.add(p)
    await session.commit()
    return p


SCOUT_SYSTEM = """Tu es un préparateur d'échecs francophone. À partir du profil d'un adversaire et des données sur ton joueur (élo ~450, joue 1.d4 en Blanc, Française en Noir), tu produis un plan de bataille concis et actionnable.

Le plan doit :
- Recommander une ouverture spécifique pour Blanc ET pour Noir basée sur les faiblesses de l'adversaire
- Identifier les pièges à éviter (ce que l'adversaire connaît bien)
- Souligner la phase clef où exploiter l'adversaire
- Tenir en 5-8 phrases maximum, ton direct, pas de jargon excessif"""


def _format_for_llm(report: ScoutReport) -> str:
    o = report.opening_report
    lines = [
        f"Adversaire: {report.opponent_username}",
        f"Parties analysées: {o.games_seen}",
        f"Sort du livre vers le coup {o.avg_out_of_book_ply or '?':.1f}" if o.avg_out_of_book_ply else "",
        "",
        "Premier coup en Blanc:",
    ]
    for m in o.first_move_as_white:
        lines.append(f"  - {m.san}: {m.games} parties, winrate {m.winrate:.0%}")
    lines.append("\nRéponses à 1.e4 (Noir):")
    for m in o.response_to_e4:
        lines.append(f"  - 1...{m.san}: {m.games} parties, winrate {m.winrate:.0%}")
    lines.append("\nRéponses à 1.d4 (Noir):")
    for m in o.response_to_d4:
        lines.append(f"  - 1...{m.san}: {m.games} parties, winrate {m.winrate:.0%}")
    lines.append("\nTop ouvertures (Blanc):")
    for op in o.top_openings_white:
        lines.append(f"  - {op.eco} {op.name}: {op.games} parties, wr {op.winrate:.0%}")
    lines.append("\nTop ouvertures (Noir):")
    for op in o.top_openings_black:
        lines.append(f"  - {op.eco} {op.name}: {op.games} parties, wr {op.winrate:.0%}")
    lines.append("\nFaiblesses détectées (sévérité 0-1):")
    for w in report.weaknesses[:6]:
        phase = f" [{w['phase']}]" if w.get("phase") else ""
        lines.append(
            f"  - {w['category']}{phase}: sev={w['severity']:.2f}, occ={w['occurrences']}"
        )
    return "\n".join([ln for ln in lines if ln is not None])


async def scout_opponent(
    session: AsyncSession,
    opponent_username: str,
    max_months: int = 3,
    max_games: int = 100,
    generate_plan: bool = True,
) -> ScoutReport:
    started = time.perf_counter()

    # 1. Import opponent's recent games
    import_stats = await import_recent_months(
        session, opponent_username, max_months=max_months, max_games=max_games
    )

    # 2. Resolve opponent Player row (created by importer)
    opponent = await _get_or_create_opponent(session, opponent_username)

    # 3. Out-of-book + opening detection on opponent's games
    await compute_out_of_book_for_all_my_games(session, opponent)
    await session.commit()

    # 4. Weakness detection (detectors are player-agnostic)
    w_report = await refresh_player_weaknesses(session, opponent)

    # 5. Opening profile
    opening_report = await compute_opening_report(session, opponent)

    # 5b. Profile, phase quality, vs my repertoire (the new intel)
    profile = await compute_opponent_profile(session, opponent)
    phase_quality = await compute_phase_quality(session, opponent)
    me_row = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    vs_my_repertoire: list[RepertoireBranch] = []
    vs_learning_openings: list[LearningOpeningProbe] = []
    if me_row:
        vs_my_repertoire = await compute_vs_my_repertoire(session, me_row, opponent)
        vs_learning_openings = await compute_vs_learning_openings(session, me_row, opponent)

    # Pull persisted Weakness rows for output
    w_rows = list((await session.execute(
        select(Weakness).where(Weakness.player_id == opponent.id)
        .order_by(Weakness.severity.desc())
    )).scalars())
    weaknesses_out = [
        {
            "category": w.category,
            "phase": w.phase,
            "severity": round(w.severity, 3),
            "occurrences": w.occurrences,
            "details": w.details,
            "sample_game_ids": (w.sample_game_ids or [])[:5],
        }
        for w in w_rows
    ]

    report = ScoutReport(
        opponent_username=opponent.chesscom_username,
        games_imported=import_stats.imported,
        games_skipped=import_stats.skipped,
        opening_report=opening_report,
        weaknesses=weaknesses_out,
        profile=profile,
        phase_quality=phase_quality,
        vs_my_repertoire=vs_my_repertoire,
        vs_learning_openings=vs_learning_openings,
        battle_plan=None,
        elapsed_s=time.perf_counter() - started,
    )

    # Deterministic plan — always built, instantaneous, regardless of LLM flag
    report.structured_plan = generate_deterministic_plan(
        profile, phase_quality, opening_report, weaknesses_out,
    )

    # 6. LLM synthesis (optional)
    if generate_plan:
        try:
            prompt = _format_for_llm(report)
            async with OllamaClient() as client:
                plan = await client.chat(
                    [
                        ChatMessage(role="system", content=SCOUT_SYSTEM),
                        ChatMessage(role="user", content=prompt + "\n\nProduis le plan de bataille."),
                    ],
                    temperature=0.4,
                    num_predict=220,
                )
            report.battle_plan = plan
        except Exception as e:
            logger.warning("LLM battle plan failed: %r (%s)", e, type(e).__name__)
            report.battle_plan = f"(LLM unavailable: {type(e).__name__})"

    report.elapsed_s = time.perf_counter() - started
    return report

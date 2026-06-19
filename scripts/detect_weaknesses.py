"""CLI: run all weakness detectors for me and print a readable report."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Player
from app.services.weakness_engine import refresh_player_weaknesses


def _bar(s: float, width: int = 20) -> str:
    n = int(round(max(0.0, min(1.0, s)) * width))
    return "█" * n + "░" * (width - n)


async def amain() -> int:
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
        if not me:
            print("No 'is_me' player in DB. Run the import first.")
            return 1
        report = await refresh_player_weaknesses(session, me)

    print(f"\n=== Weakness report for {me.chesscom_username} ===")
    print(f"Detectors run: {report.detectors_run}  |  Findings: {report.findings_emitted}\n")

    if not report.findings:
        print("No weaknesses detected yet. If Stockfish analysis is still")
        print("running, more findings will appear as games get analyzed.\n")
        return 0

    findings_sorted = sorted(report.findings, key=lambda f: -f.severity)
    for f in findings_sorted:
        phase = f" [{f.phase}]" if f.phase else ""
        print(f"  {_bar(f.severity)} {f.severity:.2f}  {f.category}{phase}")
        print(f"       occurrences={f.occurrences}  samples={f.sample_game_ids[:3]}")
        if f.details:
            short = {k: v for k, v in f.details.items() if k != "examples"}
            print(f"       details: {json.dumps(short, ensure_ascii=False)[:200]}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))

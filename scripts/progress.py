"""Take a snapshot now and print a textual progress report.

Usage:
    uv run python scripts/progress.py           # take snapshot + show today
    uv run python scripts/progress.py --days 30 # show last 30 days time series
    uv run python scripts/progress.py --no-snapshot  # just print existing series
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import MetricSnapshot, Player
from app.services.progress import take_snapshot


def _delta(a, b):
    if a is None or b is None:
        return "—"
    d = a - b
    if isinstance(d, float):
        return f"{d:+.3f}"
    return f"{d:+d}"


async def amain(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
        if not me:
            print("No 'is_me' player.")
            return 1

        if not args.no_snapshot:
            snap = await take_snapshot(session, me)
            print(f"Snapshot taken at {snap.taken_at.isoformat()}")

        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        rows = list((await session.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.player_id == me.id)
            .where(MetricSnapshot.taken_at >= since)
            .order_by(MetricSnapshot.taken_at.asc())
        )).scalars())

    print(f"\n=== Progress for {me.chesscom_username} — last {args.days} days ===")
    print(f"Snapshots in window: {len(rows)}")
    if not rows:
        print("(empty — take more snapshots over time)")
        return 0

    first = rows[0]
    last = rows[-1]

    print("\n  Metric                 Latest    Δ since first")
    print(f"  rating_rapid           {last.rating_rapid or '-':<8}  {_delta(last.rating_rapid, first.rating_rapid)}")
    print(f"  winrate_white          {last.winrate_white:<8.3f}  {_delta(last.winrate_white, first.winrate_white)}" if last.winrate_white is not None else "  winrate_white           -")
    print(f"  winrate_black          {last.winrate_black:<8.3f}  {_delta(last.winrate_black, first.winrate_black)}" if last.winrate_black is not None else "  winrate_black           -")
    print(f"  games_total            {last.games_total:<8}  {_delta(last.games_total, first.games_total)}")
    print(f"  exercises_solved_total {last.exercises_solved_total:<8}  {_delta(last.exercises_solved_total, first.exercises_solved_total)}")
    print(f"  rep_cards_reviewed_7d  {last.rep_cards_reviewed_7d:<8}")
    print(f"  plans_completed_7d     {last.plans_completed_7d:<8}")
    print(f"  repertoire_due         {last.repertoire_due or 0:<8}")
    print(f"  exercises_due          {last.exercises_due or 0:<8}")

    # Weakness severity drift
    print("\n  Weakness severities — latest:")
    sevs = last.weakness_severities or {}
    for cat, sev in sorted(sevs.items(), key=lambda kv: -kv[1])[:12]:
        first_sev = (first.weakness_severities or {}).get(cat)
        d = _delta(sev, first_sev) if first_sev is not None else "(new)"
        print(f"    {cat:<32} {sev:.2f}   Δ {d}")

    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--no-snapshot", action="store_true")
    raise SystemExit(asyncio.run(amain(p.parse_args())))

"""Generate (or refresh) the current week's coach report."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Player
from app.services.weekly_report import generate_weekly_report


async def main(force: bool = False) -> int:
    async with SessionLocal() as s:
        me = (await s.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        r = await generate_weekly_report(s, me, force=force)
    print(f"\n=== Weekly report for {me.chesscom_username} — {r.week_start} → {r.week_end} ===")
    print(f"Games played:      {r.games_played}")
    print(f"Elo delta (rapid): {r.elo_delta:+d}")
    print(f"Puzzles solved:    {r.puzzles_solved}")
    print(f"Cards reviewed:    {r.rep_cards_reviewed}")
    print(f"Plans completed:   {r.plans_completed}")
    print(f"Blunders this week:{r.blunders_this_week}")
    if r.weakness_deltas:
        print("\nWeakness deltas (negative = improved):")
        for k, v in sorted(r.weakness_deltas.items(), key=lambda kv: kv[1]):
            print(f"  {k:>30}  {v:+.3f}")
    if r.top_focus_for_next_week:
        print(f"\nTop focus for next week: {r.top_focus_for_next_week}")
    if r.narrative:
        print(f"\n--- Coach narrative ---\n{r.narrative}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(force="--force" in sys.argv)))

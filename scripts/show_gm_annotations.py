"""Show the user's repertoire nodes annotated with GM frequencies."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import RepertoireNode


async def main() -> int:
    async with SessionLocal() as s:
        rows = list((await s.execute(
            select(RepertoireNode)
            .where(RepertoireNode.gm_annotated_at.is_not(None))
            .order_by(RepertoireNode.gm_total_games.desc().nullslast())
            .limit(10)
        )).scalars())
        if not rows:
            print("No GM annotations yet. Run scripts/annotate_repertoire.py first.")
            return 0
        for n in rows:
            print(f"\n--- Node #{n.id}  ({n.color})  {n.gm_total_games:,} GM games ---")
            print(f"  Your move    : {n.move_san}")
            if n.gm_my_move_share is not None:
                print(f"  GMs play it  : {n.gm_my_move_share * 100:.1f}% of the time")
            if n.gm_my_move_score is not None:
                print(f"  Score in GM  : {n.gm_my_move_score * 100:.1f}% (W+½D)")
            print(f"  Top GM moves :")
            for m in (n.gm_moves or [])[:5]:
                marker = "  ← YOU" if m["uci"] == n.move_uci else ""
                print(f"    {m['san']:>6}  {m['share'] * 100:>5.1f}%  score={m['score_white'] * 100:.1f}%  n={m['games']:,}{marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

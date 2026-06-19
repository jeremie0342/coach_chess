"""Compute your chess style vector + GM archetype match."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Player
from app.services.personality import compute_personality


def _bar(v: float, width: int = 30) -> str:
    n = int(round(v * width))
    return "█" * n + "░" * (width - n)


async def main() -> int:
    async with SessionLocal() as s:
        me = (await s.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one()
        r = await compute_personality(s, me)
    print(f"\n=== Personality — {r.player}  ({r.moves_used} moves analyzed) ===\n")
    for trait, val in r.style.as_dict().items():
        print(f"  {trait:>16}  {_bar(val)}  {val:.2f}")
    print(f"\nDominant trait : {r.dominant_trait}")
    print(f"\nGM matches (cosine similarity):")
    for name, sim in r.matches:
        print(f"  {name:<12}  {sim:.3f}")
    print(f"\nNotes:\n  {r.notes}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

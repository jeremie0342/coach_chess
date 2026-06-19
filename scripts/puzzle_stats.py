"""Show puzzle catalog stats after Lichess ingest."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import func, select
from app.db.session import SessionLocal
from app.models import Exercise


async def main() -> int:
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(Exercise.source_kind, func.count(Exercise.id))
            .group_by(Exercise.source_kind)
        )).all()
        print("=== Puzzles by source ===")
        total = 0
        for src, n in rows:
            print(f"  {src or '(null)':>10}: {n:,}")
            total += n
        print(f"  {'TOTAL':>10}: {total:,}")

        # Difficulty histogram bins of 200
        print("\n=== Difficulty distribution ===")
        bins = (await s.execute(
            select(
                (func.floor(Exercise.difficulty / 200) * 200).label("bucket"),
                func.count(Exercise.id),
            )
            .group_by("bucket")
            .order_by("bucket")
        )).all()
        for bucket, n in bins:
            if bucket is None:
                continue
            b = int(bucket)
            print(f"  {b:>4}-{b+199:<4}: {n:>10,}  {'#' * min(40, n // 5000)}")

        # Around your ELO (464)
        in_window = (await s.execute(
            select(func.count(Exercise.id))
            .where(Exercise.difficulty.between(314, 614))
        )).scalar_one()
        print(f"\n  In your window (314-614 ELO): {in_window:,}")

        # Top 10 themes
        print("\n=== Top themes (Lichess) ===")
        themes = (await s.execute(
            select(
                func.jsonb_array_elements_text(Exercise.theme_tags).label("th"),
                func.count("*"),
            )
            .where(Exercise.source_kind == "lichess")
            .group_by("th")
            .order_by(func.count("*").desc())
            .limit(15)
        )).all()
        for th, n in themes:
            print(f"  {th:>18}: {n:>10,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

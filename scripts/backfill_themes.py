"""Tag existing MoveAnalysis rows with tactical themes.

Idempotent: skips rows that already have a non-empty `tags`.
Run after deploying the classifier on already-analyzed games.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models import Move, MoveAnalysis
from app.models.analysis import MoveQuality
from app.services.tactical_themes import ClassifyInput, classify_themes


CHUNK = 500


async def main(force: bool = False) -> int:
    start = time.perf_counter()
    tagged = scanned = skipped = 0
    async with SessionLocal() as s:
        q = (
            select(MoveAnalysis.id, MoveAnalysis.best_move_uci, MoveAnalysis.pv,
                   MoveAnalysis.eval_cp_before, MoveAnalysis.eval_mate_before,
                   Move.uci, Move.fen_before)
            .join(Move, Move.id == MoveAnalysis.move_id)
            .where(MoveAnalysis.quality.in_((
                MoveQuality.BLUNDER, MoveQuality.MISTAKE, MoveQuality.INACCURACY,
            )))
        )
        if not force:
            q = q.where(MoveAnalysis.tags.is_(None))
        rows = (await s.execute(q)).all()
        total = len(rows)
        print(f"Scanning {total} analyses...")

        batch_updates = []
        for r in rows:
            scanned += 1
            tags = classify_themes(ClassifyInput(
                fen_before=r.fen_before,
                played_uci=r.uci,
                best_uci=r.best_move_uci,
                pv_uci=r.pv,
                eval_cp_before=r.eval_cp_before,
                eval_mate_before=r.eval_mate_before,
            ))
            if tags:
                batch_updates.append((r.id, tags))
                tagged += 1
            else:
                skipped += 1

            if len(batch_updates) >= CHUNK:
                for aid, tg in batch_updates:
                    await s.execute(update(MoveAnalysis).where(MoveAnalysis.id == aid).values(tags=tg))
                await s.commit()
                batch_updates.clear()
                print(f"  ...{scanned}/{total} (tagged so far: {tagged})", flush=True)

        for aid, tg in batch_updates:
            await s.execute(update(MoveAnalysis).where(MoveAnalysis.id == aid).values(tags=tg))
        await s.commit()

    elapsed = time.perf_counter() - start
    print(f"\nDone in {elapsed:.1f}s. scanned={scanned} tagged={tagged} no-tag={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(force="--force" in sys.argv)))

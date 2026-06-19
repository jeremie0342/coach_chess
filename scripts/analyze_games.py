"""CLI: run Stockfish analysis on games.

Usage:
    uv run python scripts/analyze_games.py --all                  # all pending
    uv run python scripts/analyze_games.py --limit 10
    uv run python scripts/analyze_games.py --game-id 42
    uv run python scripts/analyze_games.py --all --depth 18
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import case, func, or_, select

from app.db.session import SessionLocal
from app.models import Game, Player
from app.services.analyzer import analyze_game
from app.services.stockfish import get_engine, shutdown_engine


async def amain(args: argparse.Namespace) -> int:
    engine = await get_engine()

    async with SessionLocal() as session:
        if args.game_id:
            games = list(
                (
                    await session.execute(select(Game).where(Game.id == args.game_id))
                ).scalars()
            )
        else:
            q = select(Game).where(Game.analysis_status == "pending")
            if args.since_rating:
                me = (await session.execute(
                    select(Player).where(Player.is_me.is_(True))
                )).scalar_one()
                my_rating = case(
                    (Game.white_player_id == me.id, Game.white_rating),
                    else_=Game.black_rating,
                )
                # Find the first time I crossed the threshold
                threshold_played_at = (await session.execute(
                    select(Game.played_at)
                    .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
                    .where(my_rating >= args.since_rating)
                    .order_by(Game.played_at.asc())
                    .limit(1)
                )).scalar()
                if threshold_played_at is None:
                    print(f"Never reached rating {args.since_rating}. Nothing to do.")
                    return 0
                q = q.where(
                    or_(Game.white_player_id == me.id, Game.black_player_id == me.id)
                ).where(Game.played_at >= threshold_played_at)
            q = q.order_by(
                Game.played_at.desc() if args.recent else Game.played_at.asc()
            )
            if args.limit:
                q = q.limit(args.limit)
            games = list((await session.execute(q)).scalars())

        total = len(games)
        if not total:
            print("No games to analyze.")
            return 0

        # Estimate from average move count
        avg_plies = (await session.execute(
            select(func.coalesce(func.avg(Game.ply_count), 0))
        )).scalar_one()
        print(f"To analyze: {total} games (~{int(avg_plies)} plies avg, depth={args.depth or 'env default'})")

        run_start = time.perf_counter()
        cumulative = {"moves": 0, "blunders": 0, "mistakes": 0, "inacc": 0}

        for i, g in enumerate(games, start=1):
            t0 = time.perf_counter()
            stats = await analyze_game(session, g, engine, depth=args.depth, force=args.force)
            dt = time.perf_counter() - t0
            cumulative["moves"] += stats.moves_analyzed
            cumulative["blunders"] += stats.blunders
            cumulative["mistakes"] += stats.mistakes
            cumulative["inacc"] += stats.inaccuracies

            elapsed = time.perf_counter() - run_start
            avg_per_game = elapsed / i
            eta_s = avg_per_game * (total - i)
            eta_min = eta_s / 60

            print(
                f"[{i}/{total}] game#{g.id} "
                f"moves={stats.moves_analyzed} "
                f"B={stats.blunders} M={stats.mistakes} I={stats.inaccuracies} "
                f"({dt:.1f}s)  "
                f"ETA {eta_min:.1f} min",
                flush=True,
            )

        total_min = (time.perf_counter() - run_start) / 60
        print(
            f"\nDone in {total_min:.1f} min. "
            f"Total: {cumulative['moves']} moves, "
            f"{cumulative['blunders']} blunders, "
            f"{cumulative['mistakes']} mistakes, "
            f"{cumulative['inacc']} inaccuracies."
        )

    await shutdown_engine()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="Analyze all pending games")
    g.add_argument("--game-id", type=int, help="Analyze a single game")
    p.add_argument("--limit", type=int, help="Cap total games to analyze")
    p.add_argument("--depth", type=int, help="Override Stockfish depth")
    p.add_argument("--since-rating", type=int, help="Only analyze games from when my rating first reached this value")
    p.add_argument("--recent", action="store_true", help="Pick most-recent games first (vs oldest)")
    p.add_argument("--force", action="store_true", help="Re-analyze even if MoveAnalysis rows exist")
    args = p.parse_args()
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())

"""Annotate the user's repertoire nodes with Lichess masters DB data."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RepertoireNode
from app.services.lichess_explorer import ExplorerClient

logger = logging.getLogger(__name__)


@dataclass
class AnnotateStats:
    annotated: int = 0
    skipped_no_data: int = 0
    skipped_existing: int = 0
    failed: int = 0
    elapsed_s: float = 0.0


async def annotate_node(
    session: AsyncSession,
    node: RepertoireNode,
    client: ExplorerClient,
) -> bool:
    """Annotate one repertoire node with masters DB info. Returns True if updated."""
    try:
        result = await client.query(node.fen, db="masters", moves=12, top_games=0)
    except Exception as e:
        logger.warning("Explorer query failed for node %d: %s", node.id, e)
        return False
    if result.total_games == 0:
        return False

    # Find my move's score in the masters data
    my_move_share = None
    my_move_score = None
    if node.move_uci:
        for m in result.moves:
            if m.uci == node.move_uci:
                my_move_share = round(m.games / max(result.total_games, 1), 4)
                # Score from the side-to-move POV
                from app.models.repertoire import RepertoireColor
                if node.color == RepertoireColor.WHITE:
                    my_move_score = round(m.score_white, 4)
                else:
                    my_move_score = round(1 - m.score_white, 4)
                break

    node.gm_total_games = result.total_games
    node.gm_moves = [
        {
            "uci": m.uci,
            "san": m.san,
            "games": m.games,
            "share": round(m.games / max(result.total_games, 1), 4),
            "score_white": round(m.score_white, 4),
            "avg_rating": m.avg_rating,
        }
        for m in result.moves[:8]
    ]
    node.gm_my_move_share = my_move_share
    node.gm_my_move_score = my_move_score
    node.gm_annotated_at = datetime.now(timezone.utc)
    return True


async def annotate_repertoire(
    session: AsyncSession,
    limit: int = 50,
    skip_existing: bool = True,
    min_my_play_count: int | None = None,
) -> AnnotateStats:
    import time
    started = time.perf_counter()
    stats = AnnotateStats()

    q = select(RepertoireNode).where(RepertoireNode.is_my_move.is_(True))
    if skip_existing:
        q = q.where(RepertoireNode.gm_annotated_at.is_(None))
    # Most-played positions first (label length is a decent proxy)
    from sqlalchemy import func
    q = q.order_by(func.length(RepertoireNode.label).desc()).limit(limit)

    nodes = list((await session.execute(q)).scalars())
    if not nodes:
        stats.elapsed_s = time.perf_counter() - started
        return stats

    async with ExplorerClient() as client:
        for i, node in enumerate(nodes, start=1):
            if skip_existing and node.gm_annotated_at is not None:
                stats.skipped_existing += 1
                continue
            try:
                ok = await annotate_node(session, node, client)
            except Exception as e:
                logger.warning("Failed to annotate node %d: %s", node.id, e)
                stats.failed += 1
                continue
            if ok:
                stats.annotated += 1
            else:
                stats.skipped_no_data += 1
            # Commit every 10 to be Ctrl+C safe
            if i % 10 == 0:
                await session.commit()
        await session.commit()

    stats.elapsed_s = time.perf_counter() - started
    logger.info(
        "annotate_repertoire: annotated=%d no_data=%d failed=%d in %.1fs",
        stats.annotated, stats.skipped_no_data, stats.failed, stats.elapsed_s,
    )
    return stats

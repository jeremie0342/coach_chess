from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import RepertoireNode
from app.services.lichess_explorer import ExplorerClient
from app.services.repertoire_annotator import annotate_repertoire

router = APIRouter(tags=["explorer"])


@router.get("/openings/explorer")
async def query_explorer(
    fen: str,
    db: Annotated[Literal["masters", "lichess"], Query()] = "masters",
    ratings: str | None = "2000,2200,2500",
    speeds: str | None = "blitz,rapid,classical",
) -> dict:
    async with ExplorerClient() as client:
        try:
            r = await client.query(fen, db=db, ratings=ratings, speeds=speeds)
        except Exception as e:
            raise HTTPException(502, f"Lichess explorer failed: {e}") from e
    return {
        "db": r.db,
        "fen_epd": r.fen_epd,
        "total_games": r.total_games,
        "white": r.white, "draws": r.draws, "black": r.black,
        "moves": [
            {"uci": m.uci, "san": m.san, "games": m.games,
             "share": round(m.games / max(r.total_games, 1), 4),
             "score_white": round(m.score_white, 4),
             "avg_rating": m.avg_rating}
            for m in r.moves
        ],
    }


@router.post("/repertoire/me/annotate")
async def trigger_annotate(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    force: bool = False,
) -> dict:
    stats = await annotate_repertoire(session, limit=limit, skip_existing=not force)
    return {
        "annotated": stats.annotated,
        "no_data": stats.skipped_no_data,
        "skipped_existing": stats.skipped_existing,
        "failed": stats.failed,
        "elapsed_s": round(stats.elapsed_s, 2),
    }


@router.get("/repertoire/me/with_gm")
async def repertoire_with_gm(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    rows = list((await session.execute(
        select(RepertoireNode)
        .where(RepertoireNode.is_my_move.is_(True))
        .where(RepertoireNode.gm_annotated_at.is_not(None))
        .order_by(RepertoireNode.gm_total_games.desc().nullslast())
        .limit(limit)
    )).scalars())
    return {
        "count": len(rows),
        "nodes": [
            {
                "id": n.id, "color": str(n.color), "fen": n.fen,
                "my_move": n.move_san,
                "my_move_share_in_gm": n.gm_my_move_share,
                "my_move_score_in_gm": n.gm_my_move_score,
                "gm_total_games": n.gm_total_games,
                "gm_moves": (n.gm_moves or [])[:5],
            }
            for n in rows
        ],
    }

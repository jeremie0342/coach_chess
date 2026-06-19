from __future__ import annotations

from fastapi import APIRouter

from app.services.tablebase import has_local_tables, probe

router = APIRouter(prefix="/tablebase", tags=["tablebase"])


@router.get("/probe")
async def probe_endpoint(fen: str) -> dict:
    p = await probe(fen)
    return {
        "fen": p.fen,
        "pieces": p.pieces,
        "wdl": p.wdl,
        "dtz": p.dtz,
        "verdict": p.verdict,
        "source": p.source,
        "has_local_tables": has_local_tables(),
    }


@router.get("/status")
async def status() -> dict:
    return {"has_local_tables": has_local_tables()}

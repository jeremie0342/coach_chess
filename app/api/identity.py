"""Expose the coach owner's identity to the frontend.

Single-user local app: there is one configured owner (chesscom_username from
.env). The frontend reads this endpoint instead of hardcoding the username.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get("", summary="Configured coach owner (Chess.com + optional Lichess)")
async def get_identity() -> dict:
    s = get_settings()
    return {
        "chesscom_username": s.chesscom_username,
        "lichess_username": getattr(s, "lichess_username", None),
        "display_name": getattr(s, "coach_display_name", None) or s.chesscom_username,
    }

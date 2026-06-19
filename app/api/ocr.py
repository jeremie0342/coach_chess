from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.services.board_ocr import fen_summary, image_to_fen

router = APIRouter(prefix="/board", tags=["board-ocr"])


@router.post("/ocr")
async def board_ocr(
    file: Annotated[UploadFile, File(description="PNG/JPG of a board screenshot")],
    side_to_move: Annotated[str, Query(pattern="^[wb]$")] = "w",
    flip: bool = False,
) -> dict:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "expected an image upload")
    data = await file.read()
    try:
        result = image_to_fen(data, side_to_move=side_to_move, flip=flip)
    except Exception as e:
        raise HTTPException(500, f"OCR failed: {e}")
    return fen_summary(result)

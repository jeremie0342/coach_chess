from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.webhooks import WebhookField, WebhookMessage, notify

router = APIRouter(prefix="/notify", tags=["notify"])


class NotifyField(BaseModel):
    name: str
    value: str
    inline: bool = True


class NotifyIn(BaseModel):
    title: str
    description: str | None = None
    color: int = Field(0x769656, ge=0, le=0xFFFFFF)
    fields: list[NotifyField] | None = None
    image_url: str | None = None
    url: str | None = None
    footer: str | None = "coach_chess"


@router.post("/", summary="Push a notification to all configured webhooks")
async def send(payload: NotifyIn) -> dict:
    msg = WebhookMessage(
        title=payload.title,
        description=payload.description,
        color=payload.color,
        fields=[WebhookField(f.name, f.value, f.inline) for f in (payload.fields or [])],
        image_url=payload.image_url,
        url=payload.url,
        footer=payload.footer,
    )
    res = await notify(msg)
    if not res["sent"]:
        raise HTTPException(400, res.get("reason") or "no webhooks configured")
    return res

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.webhooks import WebhookField, WebhookMessage, notify

router = APIRouter(prefix="/notify", tags=["notify"])


@router.get("/status", summary="Which webhook destinations are configured")
async def status() -> dict:
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "discord_configured": bool(settings.discord_webhook_url),
        "slack_configured": bool(settings.slack_webhook_url),
        "any_configured": bool(settings.discord_webhook_url or settings.slack_webhook_url),
    }


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

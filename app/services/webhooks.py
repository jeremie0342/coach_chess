"""Outgoing webhook notifications to Discord / Slack.

Both platforms expose simple "incoming webhook" URLs that accept a POST
with a JSON body. We auto-detect which one based on the URL prefix.

Configure via .env:
  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

Either or both can be set. `notify()` posts to every URL that is set.
If neither is configured, it's a no-op.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class WebhookField:
    name: str
    value: str
    inline: bool = True


@dataclass
class WebhookMessage:
    title: str
    description: str | None = None
    color: int = 0x76_96_56     # green-ish, our accent
    fields: list[WebhookField] | None = None
    image_url: str | None = None
    footer: str | None = "coach_chess"
    url: str | None = None       # link the title to


def _to_discord(msg: WebhookMessage) -> dict:
    embed: dict = {
        "title": msg.title,
        "color": msg.color,
    }
    if msg.description:
        embed["description"] = msg.description
    if msg.url:
        embed["url"] = msg.url
    if msg.fields:
        embed["fields"] = [
            {"name": f.name, "value": f.value, "inline": f.inline}
            for f in msg.fields
        ]
    if msg.image_url:
        embed["image"] = {"url": msg.image_url}
    if msg.footer:
        embed["footer"] = {"text": msg.footer}
    return {"embeds": [embed]}


def _to_slack(msg: WebhookMessage) -> dict:
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": msg.title}},
    ]
    if msg.description:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": msg.description},
        })
    if msg.fields:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{f.name}*\n{f.value}"}
                for f in msg.fields[:10]
            ],
        })
    if msg.image_url:
        blocks.append({
            "type": "image",
            "image_url": msg.image_url,
            "alt_text": msg.title,
        })
    if msg.footer:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": msg.footer}],
        })
    return {"blocks": blocks, "text": msg.title}


async def _post(url: str, payload: dict, timeout: float = 10.0) -> tuple[bool, str | None]:
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "coach_chess/0.1"}) as client:
            r = await client.post(url, json=payload)
        if r.status_code >= 400:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def notify(msg: WebhookMessage) -> dict:
    """Post `msg` to every configured webhook. Returns per-platform status."""
    settings = get_settings()
    targets: list[tuple[str, str, dict]] = []
    if settings.discord_webhook_url:
        targets.append(("discord", settings.discord_webhook_url, _to_discord(msg)))
    if settings.slack_webhook_url:
        targets.append(("slack", settings.slack_webhook_url, _to_slack(msg)))

    if not targets:
        return {"ok": False, "sent": [], "reason": "no webhook URLs configured"}

    out: dict[str, dict] = {}
    for platform, url, payload in targets:
        ok, err = await _post(url, payload)
        out[platform] = {"ok": ok, "error": err}
    return {"ok": all(s["ok"] for s in out.values()), "sent": list(out.keys()), "results": out}

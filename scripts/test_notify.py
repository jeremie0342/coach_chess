"""Send a test notification through all configured webhooks."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.webhooks import WebhookField, WebhookMessage, notify


async def main() -> int:
    msg = WebhookMessage(
        title="coach_chess test",
        description="Si tu vois ce message, la config webhook est bonne.",
        fields=[
            WebhookField("Test", "OK", inline=True),
            WebhookField("Env", "dev", inline=True),
        ],
    )
    r = await notify(msg)
    print(r)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Discord – publish to a channel through an incoming webhook.

Docs: https://discord.com/developers/docs/resources/webhook#execute-webhook
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class DiscordPlatform(BasePlatform):
    key = "discord"
    name = "Discord"
    docs_url = "https://discord.com/developers/docs/resources/webhook#execute-webhook"
    required_settings = ("discord_webhook_url",)

    async def publish(self, client: httpx.AsyncClient, message: str, link: str) -> PublishOutcome:
        webhook_url = self.settings.discord_webhook_url.rstrip("/")

        # `wait=true` makes Discord return the created message object.
        response = await client.post(
            webhook_url,
            params={"wait": "true"},
            json={"content": message, "allowed_mentions": {"parse": []}},
        )
        self.ensure_success(response)
        data = self.parse_json(response)

        message_id = data.get("id")
        channel_id = data.get("channel_id")
        guild_id = data.get("guild_id")
        if not message_id or not channel_id:
            raise PlatformError("Discord did not return the created message id")

        if not guild_id:
            # Message objects from webhooks may omit guild_id; the webhook
            # object itself always contains it.
            info = await client.get(webhook_url)
            if info.is_success:
                guild_id = self.parse_json(info).get("guild_id")

        posted_url = f"https://discord.com/channels/{guild_id or '@me'}/{channel_id}/{message_id}"

        # Discord messages can only be read by members of the server.
        return PublishOutcome(
            posted_url=posted_url,
            public=False,
            posted_at=self.parse_datetime(data.get("timestamp")),
            raw=data,
        )

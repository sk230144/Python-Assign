"""Telegram – publish to a channel through the Bot API.

Docs: https://core.telegram.org/bots/api#sendmessage
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class TelegramPlatform(BasePlatform):
    key = "telegram"
    name = "Telegram"
    docs_url = "https://core.telegram.org/bots/api#sendmessage"
    required_settings = ("telegram_bot_token", "telegram_chat_id")

    API_BASE = "https://api.telegram.org"

    async def publish(self, client: httpx.AsyncClient, message: str, link: str) -> PublishOutcome:
        url = f"{self.API_BASE}/bot{self.settings.telegram_bot_token}/sendMessage"
        response = await client.post(
            url,
            json={
                "chat_id": self.settings.telegram_chat_id,
                "text": message,
                "link_preview_options": {"url": link},
            },
        )
        # Telegram returns {"ok": false, "description": "..."} on errors.
        self.ensure_success(response)
        data = self.parse_json(response)
        if not data.get("ok"):
            raise PlatformError(data.get("description") or "Telegram rejected the message")

        result = data.get("result") or {}
        message_id = result.get("message_id")
        chat = result.get("chat") or {}
        username = chat.get("username")

        if username:
            # Public channel / group: anyone can open t.me/<username>/<id>.
            posted_url = f"https://t.me/{username}/{message_id}"
            public = True
        else:
            # Private chat: link only works for members.
            chat_id = str(chat.get("id", ""))
            internal_id = chat_id[4:] if chat_id.startswith("-100") else chat_id.lstrip("-")
            posted_url = f"https://t.me/c/{internal_id}/{message_id}"
            public = False

        return PublishOutcome(
            posted_url=posted_url,
            public=public,
            posted_at=self.parse_datetime(result.get("date")),
            raw=result,
        )

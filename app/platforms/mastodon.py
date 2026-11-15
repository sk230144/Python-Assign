"""Mastodon – publish a public status (toot).

Docs: https://docs.joinmastodon.org/methods/statuses/#create
"""

from __future__ import annotations

import hashlib

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class MastodonPlatform(BasePlatform):
    key = "mastodon"
    name = "Mastodon"
    docs_url = "https://docs.joinmastodon.org/methods/statuses/#create"
    required_settings = ("mastodon_instance_url", "mastodon_access_token")

    async def publish(self, client: httpx.AsyncClient, message: str, link: str) -> PublishOutcome:
        instance = self.settings.mastodon_instance_url.rstrip("/")
        # Idempotency-Key prevents accidental duplicate toots on retries.
        idempotency_key = hashlib.sha256(message.encode("utf-8")).hexdigest()

        response = await client.post(
            f"{instance}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {self.settings.mastodon_access_token}",
                "Idempotency-Key": idempotency_key,
            },
            data={"status": message, "visibility": "public"},
        )
        self.ensure_success(response)
        data = self.parse_json(response)

        posted_url = data.get("url") or data.get("uri")
        if not posted_url:
            raise PlatformError("Mastodon did not return the status URL")

        return PublishOutcome(
            posted_url=posted_url,
            public=data.get("visibility") == "public",
            posted_at=self.parse_datetime(data.get("created_at")),
            raw=data,
        )

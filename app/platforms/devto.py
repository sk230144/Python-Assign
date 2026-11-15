"""DEV Community (dev.to, Forem) – publish the message as an article.

Docs: https://developers.forem.com/api/v1#tag/articles/operation/createArticle
"""

from __future__ import annotations

import re

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.validation import make_title


class DevToPlatform(BasePlatform):
    key = "devto"
    name = "DEV Community"
    docs_url = "https://developers.forem.com/api/v1#tag/articles/operation/createArticle"
    required_settings = ("devto_api_key",)

    API_URL = "https://dev.to/api/articles"

    def _tags(self) -> list[str]:
        # Forem allows max 4 lowercase alphanumeric tags.
        tags = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in self.settings.devto_tags.split(",")]
        return [t for t in tags if t][:4]

    async def publish(self, client: httpx.AsyncClient, message: str, link: str) -> PublishOutcome:
        title = make_title(message, link, max_length=120)
        body = f"{message}\n\n**👉 [Visit {link}]({link})**\n"

        response = await client.post(
            self.API_URL,
            headers={
                "api-key": self.settings.devto_api_key,
                "Accept": "application/vnd.forem.api-v1+json",
            },
            json={
                "article": {
                    "title": title,
                    "body_markdown": body,
                    "published": True,
                    "tags": self._tags(),
                }
            },
        )
        self.ensure_success(response)
        data = self.parse_json(response)

        posted_url = data.get("url")
        if not posted_url:
            raise PlatformError("DEV did not return the article URL")

        published = data.get("published")
        return PublishOutcome(
            posted_url=posted_url,
            public=True if published is None else bool(published),
            posted_at=self.parse_datetime(data.get("published_at") or data.get("created_at")),
            raw={"id": data.get("id"), "url": posted_url},
        )

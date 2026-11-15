"""Bluesky – publish a post through the AT Protocol XRPC API.

Docs:
  * https://docs.bsky.app/docs/get-started#create-a-session
  * https://docs.bsky.app/docs/advanced-guides/posts
  * https://docs.bsky.app/docs/advanced-guides/post-richtext (link facets)
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class BlueskyPlatform(BasePlatform):
    key = "bluesky"
    name = "Bluesky"
    docs_url = "https://docs.bsky.app/docs/advanced-guides/posts"
    required_settings = ("bluesky_service_url", "bluesky_handle", "bluesky_app_password")

    @staticmethod
    def build_link_facets(message: str, link: str) -> list[dict]:
        """Bluesky does not auto-link URLs; links are declared as facets
        with UTF-8 *byte* offsets."""
        start = message.find(link)
        if start < 0:
            return []
        byte_start = len(message[:start].encode("utf-8"))
        byte_end = byte_start + len(link.encode("utf-8"))
        return [
            {
                "index": {"byteStart": byte_start, "byteEnd": byte_end},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": link}],
            }
        ]

    async def publish(self, client: httpx.AsyncClient, message: str, link: str) -> PublishOutcome:
        service = self.settings.bluesky_service_url.rstrip("/")

        # 1. Authenticate with handle + app password.
        session_response = await client.post(
            f"{service}/xrpc/com.atproto.server.createSession",
            json={
                "identifier": self.settings.bluesky_handle,
                "password": self.settings.bluesky_app_password,
            },
        )
        self.ensure_success(session_response)
        session = self.parse_json(session_response)
        access_jwt = session.get("accessJwt")
        did = session.get("did")
        handle = session.get("handle") or self.settings.bluesky_handle
        if not access_jwt or not did:
            raise PlatformError("Bluesky session did not return an access token")

        # 2. Create the post record.
        created_at = datetime.now(timezone.utc)
        record = {
            "$type": "app.bsky.feed.post",
            "text": message,
            "createdAt": created_at.isoformat().replace("+00:00", "Z"),
            "langs": ["en"],
        }
        facets = self.build_link_facets(message, link)
        if facets:
            record["facets"] = facets

        response = await client.post(
            f"{service}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {access_jwt}"},
            json={"repo": did, "collection": "app.bsky.feed.post", "record": record},
        )
        self.ensure_success(response)
        data = self.parse_json(response)

        uri = data.get("uri", "")  # at://did:plc:xxx/app.bsky.feed.post/<rkey>
        rkey = uri.rsplit("/", 1)[-1] if uri else ""
        if not rkey:
            raise PlatformError("Bluesky did not return the post URI")

        return PublishOutcome(
            posted_url=f"https://bsky.app/profile/{handle}/post/{rkey}",
            public=True,  # Bluesky posts are always public.
            posted_at=created_at,
            raw=data,
        )

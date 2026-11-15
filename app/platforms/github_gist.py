"""GitHub Gist – publish the message as a public gist.

Docs: https://docs.github.com/en/rest/gists/gists#create-a-gist
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.validation import make_title


class GitHubGistPlatform(BasePlatform):
    key = "github_gist"
    name = "GitHub Gist"
    docs_url = "https://docs.github.com/en/rest/gists/gists#create-a-gist"
    required_settings = ("github_token",)

    API_URL = "https://api.github.com/gists"

    async def publish(self, client: httpx.AsyncClient, message: str, link: str) -> PublishOutcome:
        title = make_title(message, link)
        content = f"# {title}\n\n{message}\n\n👉 [{link}]({link})\n"

        response = await client.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "description": message,
                "public": True,
                "files": {"announcement.md": {"content": content}},
            },
        )
        self.ensure_success(response)
        data = self.parse_json(response)

        posted_url = data.get("html_url")
        if not posted_url:
            raise PlatformError("GitHub did not return the gist URL")

        return PublishOutcome(
            posted_url=posted_url,
            public=bool(data.get("public")),
            posted_at=self.parse_datetime(data.get("created_at")),
            raw={"id": data.get("id"), "html_url": posted_url},
        )

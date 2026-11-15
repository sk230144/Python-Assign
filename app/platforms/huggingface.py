"""Hugging Face Hub (LLM platform) – publish as a Community discussion.

The message is posted as a new discussion on a model / dataset / Space
repository owned by the configured account.

Docs:
  * https://huggingface.co/docs/hub/en/repositories-pull-requests-discussions
  * https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api#huggingface_hub.HfApi.create_discussion
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.validation import make_title

_REPO_PREFIX = {"model": "", "dataset": "datasets/", "space": "spaces/"}


class HuggingFacePlatform(BasePlatform):
    key = "huggingface"
    name = "Hugging Face"
    docs_url = "https://huggingface.co/docs/hub/en/repositories-pull-requests-discussions"
    required_settings = ("hf_token", "hf_repo_id")

    HUB_URL = "https://huggingface.co"

    async def publish(self, client: httpx.AsyncClient, message: str, link: str) -> PublishOutcome:
        repo_type = (self.settings.hf_repo_type or "model").strip().lower()
        if repo_type not in _REPO_PREFIX:
            raise PlatformError(f"Invalid HF_REPO_TYPE '{repo_type}' (use model, dataset or space)")
        repo_id = self.settings.hf_repo_id.strip().strip("/")

        response = await client.post(
            f"{self.HUB_URL}/api/{repo_type}s/{repo_id}/discussions",
            headers={"Authorization": f"Bearer {self.settings.hf_token}"},
            json={
                "title": make_title(message, link, max_length=150),
                "description": f"{message}\n\n👉 {link}",
                "pullRequest": False,
            },
        )
        self.ensure_success(response)
        data = self.parse_json(response)

        number = data.get("num")
        if number is None:
            raise PlatformError("Hugging Face did not return the discussion number")

        # Visibility is reported by the repo info endpoint.
        public = True
        info = await client.get(
            f"{self.HUB_URL}/api/{repo_type}s/{repo_id}",
            headers={"Authorization": f"Bearer {self.settings.hf_token}"},
        )
        if info.is_success:
            public = not bool(self.parse_json(info).get("private"))

        return PublishOutcome(
            posted_url=f"{self.HUB_URL}/{_REPO_PREFIX[repo_type]}{repo_id}/discussions/{number}",
            public=public,
            raw=data,
        )

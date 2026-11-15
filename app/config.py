"""Application configuration loaded from environment variables / .env file.

All third-party credentials are read from the environment so that no secret
ever needs to be committed to the repository. See `.env.example`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ #
    # General
    # ------------------------------------------------------------------ #
    app_name: str = "Automated Multi-Platform Posting System"
    log_level: str = "INFO"
    log_dir: str = "logs"

    # Comma separated list of platform keys to publish to, or "all".
    # Keys: telegram, discord, mastodon, bluesky, github_gist, devto, huggingface
    enabled_platforms: str = "all"

    # Network behaviour
    request_timeout: float = Field(default=15.0, gt=0)
    platform_timeout: float = Field(default=30.0, gt=0)
    verify_public_access: bool = True

    # Timezone used for the `date` / `time` fields of the response.
    timezone: str = "UTC"

    # ------------------------------------------------------------------ #
    # Telegram (Bot API)
    # ------------------------------------------------------------------ #
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None  # e.g. "@my_public_channel"

    # ------------------------------------------------------------------ #
    # Discord (Webhook)
    # ------------------------------------------------------------------ #
    discord_webhook_url: str | None = None

    # ------------------------------------------------------------------ #
    # Mastodon
    # ------------------------------------------------------------------ #
    mastodon_instance_url: str = "https://mastodon.social"
    mastodon_access_token: str | None = None

    # ------------------------------------------------------------------ #
    # Bluesky (AT Protocol)
    # ------------------------------------------------------------------ #
    bluesky_service_url: str = "https://bsky.social"
    bluesky_handle: str | None = None
    bluesky_app_password: str | None = None

    # ------------------------------------------------------------------ #
    # GitHub Gist
    # ------------------------------------------------------------------ #
    github_token: str | None = None

    # ------------------------------------------------------------------ #
    # DEV Community (Forem)
    # ------------------------------------------------------------------ #
    devto_api_key: str | None = None
    devto_tags: str = "business,marketing"

    # ------------------------------------------------------------------ #
    # Hugging Face Hub (LLM platform)
    # ------------------------------------------------------------------ #
    hf_token: str | None = None
    hf_repo_id: str | None = None  # e.g. "your-username/announcements"
    hf_repo_type: str = "model"  # model | dataset | space

    @property
    def enabled_platform_keys(self) -> list[str] | None:
        """Return the explicit list of enabled keys, or None meaning "all"."""
        raw = (self.enabled_platforms or "all").strip().lower()
        if raw in ("", "all", "*"):
            return None
        return [key.strip() for key in raw.split(",") if key.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Registry of every supported platform integration."""

from __future__ import annotations

from app.config import Settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.github_gist import GitHubGistPlatform
from app.platforms.huggingface import HuggingFacePlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform

PLATFORM_CLASSES: tuple[type[BasePlatform], ...] = (
    TelegramPlatform,
    DiscordPlatform,
    MastodonPlatform,
    BlueskyPlatform,
    GitHubGistPlatform,
    DevToPlatform,
    HuggingFacePlatform,
)

PLATFORM_KEYS = tuple(cls.key for cls in PLATFORM_CLASSES)


def is_enabled(platform_key: str, settings: Settings) -> bool:
    keys = settings.enabled_platform_keys
    return keys is None or platform_key in keys


def get_all_platforms(settings: Settings) -> list[BasePlatform]:
    return [cls(settings) for cls in PLATFORM_CLASSES]


def get_enabled_platforms(settings: Settings) -> list[BasePlatform]:
    """Platform selection is internal: driven by ENABLED_PLATFORMS."""
    return [p for p in get_all_platforms(settings) if is_enabled(p.key, settings)]


__all__ = [
    "BasePlatform",
    "PlatformError",
    "PublishOutcome",
    "PLATFORM_CLASSES",
    "PLATFORM_KEYS",
    "get_all_platforms",
    "get_enabled_platforms",
    "is_enabled",
]

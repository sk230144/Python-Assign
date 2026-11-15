"""Common building blocks shared by every platform integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

import httpx

from app.config import Settings


class PlatformError(Exception):
    """A platform rejected the request or returned an unusable response."""


class PlatformNotConfiguredError(PlatformError):
    """Required credentials for the platform are missing."""


@dataclass
class PublishOutcome:
    """What a platform integration returns after a successful post."""

    posted_url: str
    public: bool
    posted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class BasePlatform(ABC):
    """Base class for a third-party publishing integration.

    Subclasses declare:
      * ``key``              – identifier used in ``ENABLED_PLATFORMS``;
      * ``name``             – display name returned in the API response;
      * ``docs_url``         – official API documentation that was used;
      * ``required_settings``– ``Settings`` attributes that must be set;
    and implement :meth:`publish`.
    """

    key: ClassVar[str]
    name: ClassVar[str]
    docs_url: ClassVar[str]
    required_settings: ClassVar[tuple[str, ...]] = ()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------ #
    # Configuration
    # ------------------------------------------------------------------ #
    def missing_settings(self) -> list[str]:
        return [
            name.upper()
            for name in self.required_settings
            if not str(getattr(self.settings, name, "") or "").strip()
        ]

    def is_configured(self) -> bool:
        return not self.missing_settings()

    # ------------------------------------------------------------------ #
    # Publishing
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def publish(self, client: httpx.AsyncClient, message: str, link: str) -> PublishOutcome:
        """Publish ``message`` and return where it was published."""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            raise PlatformError(
                f"Unexpected non-JSON response (HTTP {response.status_code})"
            ) from None
        if not isinstance(data, dict):
            raise PlatformError(f"Unexpected response format (HTTP {response.status_code})")
        return data

    @classmethod
    def ensure_success(cls, response: httpx.Response) -> None:
        """Raise a readable :class:`PlatformError` for non-2xx responses."""
        if response.is_success:
            return

        detail = cls._extract_error_detail(response)
        status = response.status_code
        if status in (401, 403):
            prefix = "Authentication failed"
        elif status == 404:
            prefix = "Resource not found"
        elif status == 422 or status == 400:
            prefix = "Request rejected"
        elif status == 429:
            prefix = "Rate limit exceeded"
        elif status >= 500:
            prefix = "Platform server error"
        else:
            prefix = "Request failed"
        message = f"{prefix} (HTTP {status})"
        if detail:
            message += f": {detail}"
        raise PlatformError(message)

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            text = response.text.strip()
            return text[:200] if text and "<html" not in text.lower() else ""

        if isinstance(data, dict):
            for key in ("description", "error_description", "message", "error", "errors"):
                value = data.get(key)
                if not value:
                    continue
                if isinstance(value, list):
                    return "; ".join(str(v) for v in value)[:300]
                if isinstance(value, dict):
                    return str(value.get("message") or value)[:300]
                return str(value)[:300]
        return str(data)[:300]

    @staticmethod
    def parse_datetime(value: Any) -> datetime:
        """Parse an ISO-8601 string or UNIX timestamp, falling back to now()."""
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value, tz=timezone.utc)
            if isinstance(value, str) and value:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass
        return datetime.now(timezone.utc)

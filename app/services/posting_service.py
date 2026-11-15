"""Orchestrates publishing one message to every enabled platform.

* All platforms run **concurrently** (``asyncio.gather``).
* Each platform is **isolated**: any exception is converted into a
  ``failed`` result, so one failing platform never stops the others.
* Every platform call has its own overall timeout.
* After a successful post, public accessibility is optionally confirmed
  with an anonymous (unauthenticated) request to the posted URL.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.config import Settings
from app.platforms import BasePlatform, PlatformError, get_enabled_platforms
from app.schemas import PlatformResult, PostingResponse, PostingSummary, PostStatus

logger = logging.getLogger("posting")

USER_AGENT = "AutomatedPostingSystem/1.0 (+https://github.com)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class PostingService:
    def __init__(
        self,
        settings: Settings,
        platforms: list[BasePlatform] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.platforms = platforms if platforms is not None else get_enabled_platforms(settings)
        # Connection-level retries only (never re-sends a POST that reached the server).
        self.transport = transport or httpx.AsyncHTTPTransport(retries=1)
        self.tz = self._resolve_timezone(settings.timezone)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def publish(self, message: str, link: str) -> PostingResponse:
        logger.info("Publishing to %d platform(s): %s", len(self.platforms),
                    ", ".join(p.name for p in self.platforms))

        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=httpx.Timeout(self.settings.request_timeout),
            headers={"User-Agent": USER_AGENT},
        ) as client:
            results = await asyncio.gather(
                *(self._publish_one(client, platform, message, link) for platform in self.platforms)
            )

        succeeded = sum(1 for r in results if r.status == PostStatus.success)
        response = PostingResponse(
            success=succeeded > 0,
            message=message,
            cta_link=link,
            timezone=self.tz.key if isinstance(self.tz, ZoneInfo) else "UTC",
            summary=PostingSummary(
                total=len(results), succeeded=succeeded, failed=len(results) - succeeded
            ),
            results=list(results),
        )
        self._write_history(response)
        logger.info("Finished: %d succeeded, %d failed", succeeded, len(results) - succeeded)
        return response

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _publish_one(
        self, client: httpx.AsyncClient, platform: BasePlatform, message: str, link: str
    ) -> PlatformResult:
        missing = platform.missing_settings()
        if missing:
            return self._failed(platform, f"Platform not configured: set {', '.join(missing)}")

        try:
            outcome = await asyncio.wait_for(
                platform.publish(client, message, link),
                timeout=self.settings.platform_timeout,
            )
        except PlatformError as exc:
            return self._failed(platform, str(exc))
        except (asyncio.TimeoutError, httpx.TimeoutException):
            return self._failed(platform, "Request timed out")
        except httpx.ConnectError as exc:
            return self._failed(platform, f"Could not connect to the platform: {exc}")
        except httpx.HTTPError as exc:
            return self._failed(platform, f"HTTP error: {exc.__class__.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 – isolate any bug in one integration
            logger.exception("Unexpected error while posting to %s", platform.name)
            return self._failed(platform, f"Unexpected error: {exc.__class__.__name__}: {exc}")

        public = outcome.public
        if public and self.settings.verify_public_access:
            public = await self._is_publicly_accessible(client, outcome.posted_url)

        posted_at = outcome.posted_at.astimezone(self.tz)
        logger.info("[%s] success -> %s (public=%s)", platform.name, outcome.posted_url, public)
        return PlatformResult(
            platform=platform.name,
            status=PostStatus.success,
            posted_url=outcome.posted_url,
            public_access=public,
            date=posted_at.strftime("%Y-%m-%d"),
            time=posted_at.strftime("%H:%M:%S"),
            error=None,
        )

    @staticmethod
    def _failed(platform: BasePlatform, error: str) -> PlatformResult:
        logger.warning("[%s] failed -> %s", platform.name, error)
        return PlatformResult(
            platform=platform.name,
            status=PostStatus.failed,
            posted_url=None,
            public_access=False,
            date=None,
            time=None,
            error=error,
        )

    @staticmethod
    async def _is_publicly_accessible(client: httpx.AsyncClient, url: str) -> bool:
        """Anonymous GET (no credentials) – public if it resolves with < 400."""
        try:
            response = await client.get(
                url, follow_redirects=True, headers={"User-Agent": BROWSER_USER_AGENT}
            )
            return response.status_code < 400
        except httpx.HTTPError as exc:
            logger.info("Public access check failed for %s: %s", url, exc)
            return False

    @staticmethod
    def _resolve_timezone(name: str) -> ZoneInfo | timezone:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("Unknown timezone '%s', falling back to UTC", name)
            return timezone.utc

    def _write_history(self, response: PostingResponse) -> None:
        """Append every posting run to logs/posting_history.jsonl."""
        try:
            log_dir = Path(self.settings.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            entry = {"logged_at": datetime.now(timezone.utc).isoformat(), **response.model_dump(mode="json")}
            with (log_dir / "posting_history.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Could not write posting history: %s", exc)

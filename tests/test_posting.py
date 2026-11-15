"""End-to-end tests for POST /posting (third-party APIs are faked)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx

from app.main import get_posting_service
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.services.posting_service import PostingService
from tests.conftest import make_settings

VALID_MESSAGE = (
    "Check out our latest business platform and grow your online visibility. "
    "https://example.com"
)


class FakeSuccess(BasePlatform):
    key, name, docs_url = "ok", "Fake OK", "https://docs"

    async def publish(self, client, message, link):
        return PublishOutcome(
            posted_url="https://fake.example/post/1",
            public=True,
            posted_at=datetime(2026, 11, 15, 10, 30, 0, tzinfo=timezone.utc),
        )


class FakePrivate(FakeSuccess):
    key, name = "private", "Fake Private"

    async def publish(self, client, message, link):
        outcome = await super().publish(client, message, link)
        outcome.public = False
        return outcome


class FakeAuthFailure(BasePlatform):
    key, name, docs_url = "auth", "Fake Auth Failure", "https://docs"

    async def publish(self, client, message, link):
        raise PlatformError("Authentication failed (HTTP 401): bad token")


class FakeCrash(BasePlatform):
    key, name, docs_url = "crash", "Fake Crash", "https://docs"

    async def publish(self, client, message, link):
        raise RuntimeError("boom")


class FakeTimeout(BasePlatform):
    key, name, docs_url = "slow", "Fake Slow", "https://docs"

    async def publish(self, client, message, link):
        await asyncio.sleep(5)


class FakeUnconfigured(FakeSuccess):
    key, name = "unconfigured", "Fake Unconfigured"
    required_settings = ("telegram_bot_token",)


def _use_platforms(tmp_path, *platform_classes, **settings_overrides):
    settings = make_settings(tmp_path, platform_timeout=0.2, **settings_overrides)
    platforms = [cls(settings) for cls in platform_classes]
    return lambda: PostingService(settings, platforms=platforms)


# ---------------------------------------------------------------------- #
# Successful flow & isolation of failures
# ---------------------------------------------------------------------- #
def test_posting_continues_when_some_platforms_fail(client, tmp_path):
    from app.main import app

    app.dependency_overrides[get_posting_service] = _use_platforms(
        tmp_path, FakeSuccess, FakeAuthFailure, FakeCrash, FakeTimeout, FakeUnconfigured, FakePrivate
    )

    response = client.post("/posting", json={"message": VALID_MESSAGE})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["cta_link"] == "https://example.com"
    assert body["summary"] == {"total": 6, "succeeded": 2, "failed": 4}

    results = {r["platform"]: r for r in body["results"]}
    assert results["Fake OK"] == {
        "platform": "Fake OK",
        "status": "success",
        "posted_url": "https://fake.example/post/1",
        "public_access": True,
        "date": "2026-11-15",
        "time": "10:30:00",
        "error": None,
    }
    assert results["Fake Private"]["public_access"] is False
    assert results["Fake Auth Failure"]["status"] == "failed"
    assert results["Fake Auth Failure"]["error"] == "Authentication failed (HTTP 401): bad token"
    assert results["Fake Auth Failure"]["posted_url"] is None
    assert results["Fake Auth Failure"]["date"] is None
    assert "Unexpected error: RuntimeError: boom" == results["Fake Crash"]["error"]
    assert results["Fake Slow"]["error"] == "Request timed out"
    assert results["Fake Unconfigured"]["error"] == "Platform not configured: set TELEGRAM_BOT_TOKEN"


def test_success_false_when_every_platform_fails(client, tmp_path):
    from app.main import app

    app.dependency_overrides[get_posting_service] = _use_platforms(tmp_path, FakeAuthFailure)
    body = client.post("/posting", json={"message": VALID_MESSAGE}).json()
    assert body["success"] is False
    assert body["summary"]["failed"] == 1


def test_timezone_is_applied_to_date_and_time(client, tmp_path):
    from app.main import app

    app.dependency_overrides[get_posting_service] = _use_platforms(
        tmp_path, FakeSuccess, timezone="Asia/Kolkata"
    )
    body = client.post("/posting", json={"message": VALID_MESSAGE}).json()
    assert body["timezone"] == "Asia/Kolkata"
    assert body["results"][0]["time"] == "16:00:00"


def test_history_is_written(client, tmp_path):
    from app.main import app

    app.dependency_overrides[get_posting_service] = _use_platforms(tmp_path, FakeSuccess)
    client.post("/posting", json={"message": VALID_MESSAGE})
    lines = (tmp_path / "logs" / "posting_history.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["results"][0]["platform"] == "Fake OK"


def test_public_access_is_verified_anonymously(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(404)

    settings = make_settings(tmp_path, verify_public_access=True)
    service = PostingService(
        settings, platforms=[FakeSuccess(settings)], transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(service.publish(VALID_MESSAGE, "https://example.com")).results[0]
    assert result.status == "success"
    assert result.public_access is False  # URL not reachable anonymously
    assert seen["auth"] is None


# ---------------------------------------------------------------------- #
# Input validation through the API
# ---------------------------------------------------------------------- #
def _error_messages(response):
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "Validation failed"
    return [d["message"] for d in body["details"]]


def test_rejects_too_long_message(client):
    messages = _error_messages(client.post("/posting", json={"message": "a" * 200 + " https://x.com"}))
    assert "must not exceed 200 characters" in messages[0]


def test_rejects_missing_link(client):
    messages = _error_messages(client.post("/posting", json={"message": "Hello world"}))
    assert "exactly one CTA link" in messages[0]


def test_rejects_multiple_links(client):
    messages = _error_messages(
        client.post("/posting", json={"message": "https://a.com and https://b.com"})
    )
    assert "found 2" in messages[0]


def test_rejects_invalid_url(client):
    messages = _error_messages(client.post("/posting", json={"message": "Visit https://localhost"}))
    assert "public address" in messages[0]


def test_rejects_client_side_platform_selection(client):
    response = client.post(
        "/posting", json={"message": VALID_MESSAGE, "platforms": ["telegram"]}
    )
    messages = _error_messages(response)
    assert "platform selection is handled internally" in messages[0]


def test_rejects_missing_message_field(client):
    body = client.post("/posting", json={}).json()
    assert body["details"] == [{"field": "message", "message": "Field 'message' is required"}]


def test_rejects_non_string_message(client):
    messages = _error_messages(client.post("/posting", json={"message": 123}))
    assert messages == ["Field 'message' must be a string"]


def test_rejects_invalid_json(client):
    response = client.post(
        "/posting", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert "valid JSON" in _error_messages(response)[0]


def test_platforms_endpoint_never_exposes_secrets(client):
    response = client.get("/platforms")
    assert response.status_code == 200
    keys = {p["key"] for p in response.json()}
    assert keys == {"telegram", "discord", "mastodon", "bluesky", "github_gist", "devto", "huggingface"}
    for platform in response.json():
        assert set(platform) == {"key", "name", "enabled", "configured", "missing_settings", "docs_url"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}

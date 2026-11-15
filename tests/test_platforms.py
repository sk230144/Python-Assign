"""Unit tests for each platform integration using a mocked HTTP transport.

They check that each integration calls the documented endpoint with the
right authentication and payload, and parses the documented response.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.platforms.base import PlatformError
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.github_gist import GitHubGistPlatform
from app.platforms.huggingface import HuggingFacePlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform
from tests.conftest import make_settings

MESSAGE = "Grow your online visibility today. https://example.com"
LINK = "https://example.com"


def run(platform, handler):
    async def _run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await platform.publish(client, MESSAGE, LINK)

    return asyncio.run(_run())


def body(request: httpx.Request) -> dict:
    return json.loads(request.content)


# ---------------------------------------------------------------- Telegram
def test_telegram_public_channel(tmp_path):
    settings = make_settings(tmp_path, telegram_bot_token="123:ABC", telegram_chat_id="@mychan")

    def handler(request):
        assert request.url.path == "/bot123:ABC/sendMessage"
        assert body(request)["chat_id"] == "@mychan"
        assert body(request)["text"] == MESSAGE
        return httpx.Response(200, json={
            "ok": True,
            "result": {"message_id": 42, "date": 1763202600,
                       "chat": {"id": -1001234, "username": "mychan", "type": "channel"}},
        })

    outcome = run(TelegramPlatform(settings), handler)
    assert outcome.posted_url == "https://t.me/mychan/42"
    assert outcome.public is True
    assert outcome.posted_at.year == 2025


def test_telegram_private_channel(tmp_path):
    settings = make_settings(tmp_path, telegram_bot_token="t", telegram_chat_id="-1001234")

    def handler(request):
        return httpx.Response(200, json={
            "ok": True, "result": {"message_id": 7, "date": 0, "chat": {"id": -1001234}}})

    outcome = run(TelegramPlatform(settings), handler)
    assert outcome.posted_url == "https://t.me/c/1234/7"
    assert outcome.public is False


def test_telegram_error_description_is_reported(tmp_path):
    settings = make_settings(tmp_path, telegram_bot_token="t", telegram_chat_id="@x")

    def handler(request):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(PlatformError, match=r"Request rejected \(HTTP 400\): Bad Request: chat not found"):
        run(TelegramPlatform(settings), handler)


# ---------------------------------------------------------------- Discord
def test_discord_webhook(tmp_path):
    webhook = "https://discord.com/api/webhooks/1/tok"
    settings = make_settings(tmp_path, discord_webhook_url=webhook)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"guild_id": "999", "channel_id": "555"})
        assert request.url.params["wait"] == "true"
        assert body(request)["content"] == MESSAGE
        return httpx.Response(200, json={"id": "777", "channel_id": "555",
                                         "timestamp": "2026-11-15T10:30:00+00:00"})

    outcome = run(DiscordPlatform(settings), handler)
    assert outcome.posted_url == "https://discord.com/channels/999/555/777"
    assert outcome.public is False


def test_discord_invalid_webhook(tmp_path):
    settings = make_settings(tmp_path, discord_webhook_url="https://discord.com/api/webhooks/1/x")

    def handler(request):
        return httpx.Response(401, json={"message": "Invalid Webhook Token", "code": 50027})

    with pytest.raises(PlatformError, match="Authentication failed .*Invalid Webhook Token"):
        run(DiscordPlatform(settings), handler)


# ---------------------------------------------------------------- Mastodon
def test_mastodon_status(tmp_path):
    settings = make_settings(tmp_path, mastodon_instance_url="https://mastodon.social/",
                             mastodon_access_token="tok")

    def handler(request):
        assert str(request.url) == "https://mastodon.social/api/v1/statuses"
        assert request.headers["Authorization"] == "Bearer tok"
        assert "Idempotency-Key" in request.headers
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        assert form["visibility"] == "public"
        return httpx.Response(200, json={"url": "https://mastodon.social/@me/1", "visibility": "public",
                                         "created_at": "2026-11-15T10:30:00.000Z"})

    outcome = run(MastodonPlatform(settings), handler)
    assert outcome.posted_url == "https://mastodon.social/@me/1"
    assert outcome.public is True


# ---------------------------------------------------------------- Bluesky
def test_bluesky_post_with_link_facet(tmp_path):
    settings = make_settings(tmp_path, bluesky_handle="me.bsky.social", bluesky_app_password="pw")

    def handler(request):
        if request.url.path.endswith("createSession"):
            assert body(request) == {"identifier": "me.bsky.social", "password": "pw"}
            return httpx.Response(200, json={"accessJwt": "jwt", "did": "did:plc:abc",
                                             "handle": "me.bsky.social"})
        assert request.headers["Authorization"] == "Bearer jwt"
        record = body(request)["record"]
        assert record["text"] == MESSAGE
        facet = record["facets"][0]
        start, end = facet["index"]["byteStart"], facet["index"]["byteEnd"]
        assert MESSAGE.encode()[start:end].decode() == LINK
        return httpx.Response(200, json={"uri": "at://did:plc:abc/app.bsky.feed.post/3kxyz",
                                         "cid": "c"})

    outcome = run(BlueskyPlatform(settings), handler)
    assert outcome.posted_url == "https://bsky.app/profile/me.bsky.social/post/3kxyz"
    assert outcome.public is True


def test_bluesky_facets_use_utf8_byte_offsets():
    message = "Café ☕ https://example.com"
    facet = BlueskyPlatform.build_link_facets(message, LINK)[0]
    start, end = facet["index"]["byteStart"], facet["index"]["byteEnd"]
    assert message.encode("utf-8")[start:end] == LINK.encode()


def test_bluesky_bad_password(tmp_path):
    settings = make_settings(tmp_path, bluesky_handle="me", bluesky_app_password="bad")

    def handler(request):
        return httpx.Response(401, json={"error": "AuthenticationRequired",
                                         "message": "Invalid identifier or password"})

    with pytest.raises(PlatformError, match="Invalid identifier or password"):
        run(BlueskyPlatform(settings), handler)


# ---------------------------------------------------------------- GitHub Gist
def test_github_gist(tmp_path):
    settings = make_settings(tmp_path, github_token="ghp_x")

    def handler(request):
        assert request.headers["Authorization"] == "Bearer ghp_x"
        payload = body(request)
        assert payload["public"] is True
        assert LINK in payload["files"]["announcement.md"]["content"]
        return httpx.Response(201, json={"id": "abc", "html_url": "https://gist.github.com/me/abc",
                                         "public": True, "created_at": "2026-11-15T10:30:00Z"})

    outcome = run(GitHubGistPlatform(settings), handler)
    assert outcome.posted_url == "https://gist.github.com/me/abc"
    assert outcome.public is True


# ---------------------------------------------------------------- DEV
def test_devto_article(tmp_path):
    settings = make_settings(tmp_path, devto_api_key="key", devto_tags="Business, Market-ing,x,y,z")

    def handler(request):
        assert request.headers["api-key"] == "key"
        article = body(request)["article"]
        assert article["published"] is True
        assert article["title"] == "Grow your online visibility today"
        assert article["tags"] == ["business", "marketing", "x", "y"]
        return httpx.Response(201, json={"id": 1, "url": "https://dev.to/me/grow-1",
                                         "published": True, "published_at": "2026-11-15T10:30:00Z"})

    outcome = run(DevToPlatform(settings), handler)
    assert outcome.posted_url == "https://dev.to/me/grow-1"
    assert outcome.public is True


# ---------------------------------------------------------------- Hugging Face
@pytest.mark.parametrize("repo_type, prefix", [("model", ""), ("dataset", "datasets/"),
                                                ("space", "spaces/")])
def test_huggingface_discussion(tmp_path, repo_type, prefix):
    settings = make_settings(tmp_path, hf_token="hf_x", hf_repo_id="me/repo", hf_repo_type=repo_type)

    def handler(request):
        assert request.headers["Authorization"] == "Bearer hf_x"
        if request.method == "GET":
            assert request.url.path == f"/api/{repo_type}s/me/repo"
            return httpx.Response(200, json={"id": "me/repo", "private": False})
        assert request.url.path == f"/api/{repo_type}s/me/repo/discussions"
        assert body(request)["pullRequest"] is False
        return httpx.Response(200, json={"num": 3})

    outcome = run(HuggingFacePlatform(settings), handler)
    assert outcome.posted_url == f"https://huggingface.co/{prefix}me/repo/discussions/3"
    assert outcome.public is True


def test_huggingface_private_repo(tmp_path):
    settings = make_settings(tmp_path, hf_token="hf_x", hf_repo_id="me/repo")

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"private": True})
        return httpx.Response(200, json={"num": 1})

    assert run(HuggingFacePlatform(settings), handler).public is False


# ---------------------------------------------------------------- Common
def test_non_json_error_response(tmp_path):
    settings = make_settings(tmp_path, github_token="x")

    def handler(request):
        return httpx.Response(502, text="<html>Bad gateway</html>")

    with pytest.raises(PlatformError, match=r"^Platform server error \(HTTP 502\)$"):
        run(GitHubGistPlatform(settings), handler)


def test_rate_limit_error(tmp_path):
    settings = make_settings(tmp_path, devto_api_key="x")

    def handler(request):
        return httpx.Response(429, json={"error": "Rate limit reached, try again in 30 seconds"})

    with pytest.raises(PlatformError, match="Rate limit exceeded"):
        run(DevToPlatform(settings), handler)

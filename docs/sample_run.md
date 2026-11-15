# Sample run logs

These are real outputs from running the application on 2026-11-15 (Windows 11, Python 3.12).

## 1. Test suite

```text
$ python -m pytest -q
...........................................................              [100%]
59 passed in 3.08s
```

## 2. Server start-up

```text
$ uvicorn app.main:app --host 0.0.0.0 --port 4000
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:4000 (Press CTRL+C to quit)
```

`GET http://localhost:4000/docs` → `HTTP 200` (Swagger UI).

## 3. ✅ Live run: published to all 7 platforms

Real credentials were configured in `.env`. One request published the message to every platform in **about 4 seconds**, because the platforms are called concurrently.

```text
$ curl -s localhost:4000/platforms
  Telegram       enabled=True configured=True
  Discord        enabled=True configured=True
  Mastodon       enabled=True configured=True
  Bluesky        enabled=True configured=True
  GitHub Gist    enabled=True configured=True
  DEV Community  enabled=True configured=True
  Hugging Face   enabled=True configured=True

$ curl -s -X POST localhost:4000/posting -H "Content-Type: application/json" \
    -d '{"message":"Check out our latest business platform and grow your online visibility. https://example.com"}'
HTTP 200 in 4.08s
```

```json
{
  "success": true,
  "message": "Check out our latest business platform and grow your online visibility. https://example.com",
  "cta_link": "https://example.com",
  "timezone": "UTC",
  "summary": { "total": 7, "succeeded": 7, "failed": 0 },
  "results": [
    { "platform": "Telegram", "status": "success",
      "posted_url": "https://t.me/myChannel230144/2",
      "public_access": true, "date": "2026-11-15", "time": "11:03:38", "error": null },
    { "platform": "Discord", "status": "success",
      "posted_url": "https://discord.com/channels/1571471920581578834/1571471921856643155/1571480796538216578",
      "public_access": false, "date": "2026-11-15", "time": "11:03:38", "error": null },
    { "platform": "Mastodon", "status": "success",
      "posted_url": "https://mastodon.social/@saurabh230144/117620121180382077",
      "public_access": true, "date": "2026-11-15", "time": "11:03:38", "error": null },
    { "platform": "Bluesky", "status": "success",
      "posted_url": "https://bsky.app/profile/risabht043.bsky.social/post/3n2duilo66j2z",
      "public_access": true, "date": "2026-11-15", "time": "11:03:40", "error": null },
    { "platform": "GitHub Gist", "status": "success",
      "posted_url": "https://gist.github.com/sk230144/526729320dc1b8d33c9400edf5e807af",
      "public_access": true, "date": "2026-11-15", "time": "11:03:38", "error": null },
    { "platform": "DEV Community", "status": "success",
      "posted_url": "https://dev.to/saurabh_tiwari_e2aaaf6ec7/check-out-our-latest-business-platform-and-grow-your-online-visibility-50j9",
      "public_access": true, "date": "2026-11-15", "time": "11:03:39", "error": null },
    { "platform": "Hugging Face", "status": "success",
      "posted_url": "https://huggingface.co/risabht043/announcements/discussions/1",
      "public_access": true, "date": "2026-11-15", "time": "11:03:39", "error": null }
  ]
}
```

Discord reports `public_access: false` on purpose: Discord messages can only be read by members of the server.

Application log (`logs/app.log`, local time IST = UTC+5:30), in the order the platforms finished:

```text
2026-11-15 16:33:38,854 | INFO | posting | Publishing to 7 platform(s): Telegram, Discord, Mastodon, Bluesky, GitHub Gist, DEV Community, Hugging Face
2026-11-15 16:33:39,948 | INFO | posting | [Hugging Face] success -> https://huggingface.co/risabht043/announcements/discussions/1 (public=True)
2026-11-15 16:33:40,049 | INFO | posting | [Mastodon] success -> https://mastodon.social/@saurabh230144/117620121180382077 (public=True)
2026-11-15 16:33:40,175 | INFO | posting | [Discord] success -> https://discord.com/channels/1571471920581578834/1571471921856643155/1571480796538216578 (public=False)
2026-11-15 16:33:40,582 | INFO | posting | [DEV Community] success -> https://dev.to/saurabh_tiwari_e2aaaf6ec7/check-out-our-latest-business-platform-and-grow-your-online-visibility-50j9 (public=True)
2026-11-15 16:33:40,656 | INFO | posting | [Telegram] success -> https://t.me/myChannel230144/2 (public=True)
2026-11-15 16:33:41,122 | INFO | posting | [GitHub Gist] success -> https://gist.github.com/sk230144/526729320dc1b8d33c9400edf5e807af (public=True)
2026-11-15 16:33:42,332 | INFO | posting | [Bluesky] success -> https://bsky.app/profile/risabht043.bsky.social/post/3n2duilo66j2z (public=True)
2026-11-15 16:33:42,339 | INFO | posting | Finished: 7 succeeded, 0 failed
```

## 3b. Live calls to every platform API (credentials intentionally invalid)

Every integration sent a real request to the real third-party API. Each failure
was handled on its own, the run carried on with the remaining platforms, and the
platform's own error message was passed back:

```text
[GitHub Gist]   failed -> Authentication failed (HTTP 401): Bad credentials
[Mastodon]      failed -> Authentication failed (HTTP 401): The access token is invalid
[Hugging Face]  failed -> Authentication failed (HTTP 401): Invalid username or password.
[Discord]       failed -> Resource not found (HTTP 404): Unknown Webhook
[Telegram]      failed -> Authentication failed (HTTP 401): Unauthorized
[DEV Community] failed -> Authentication failed (HTTP 401): unauthorized
[Bluesky]       failed -> Authentication failed (HTTP 401): Invalid identifier or password
```

The lines are in completion order because all platforms are called concurrently.

## 4. Request with no credentials configured

```text
$ curl -s -X POST localhost:4000/posting -H "Content-Type: application/json" \
    -d '{"message":"Check out our latest business platform and grow your online visibility. https://example.com"}'
```

```json
{
  "success": false,
  "message": "Check out our latest business platform and grow your online visibility. https://example.com",
  "cta_link": "https://example.com",
  "timezone": "UTC",
  "summary": { "total": 7, "succeeded": 0, "failed": 7 },
  "results": [
    { "platform": "Telegram", "status": "failed", "posted_url": null, "public_access": false,
      "date": null, "time": null, "error": "Platform not configured: set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID" },
    { "platform": "Discord", "status": "failed", "posted_url": null, "public_access": false,
      "date": null, "time": null, "error": "Platform not configured: set DISCORD_WEBHOOK_URL" },
    { "platform": "Mastodon", "status": "failed", "posted_url": null, "public_access": false,
      "date": null, "time": null, "error": "Platform not configured: set MASTODON_ACCESS_TOKEN" },
    { "platform": "Bluesky", "status": "failed", "posted_url": null, "public_access": false,
      "date": null, "time": null, "error": "Platform not configured: set BLUESKY_HANDLE, BLUESKY_APP_PASSWORD" },
    { "platform": "GitHub Gist", "status": "failed", "posted_url": null, "public_access": false,
      "date": null, "time": null, "error": "Platform not configured: set GITHUB_TOKEN" },
    { "platform": "DEV Community", "status": "failed", "posted_url": null, "public_access": false,
      "date": null, "time": null, "error": "Platform not configured: set DEVTO_API_KEY" },
    { "platform": "Hugging Face", "status": "failed", "posted_url": null, "public_access": false,
      "date": null, "time": null, "error": "Platform not configured: set HF_TOKEN, HF_REPO_ID" }
  ]
}
```

## 5. Validation errors (live server)

| Case | Response (HTTP 422) |
|------|---------------------|
| 215 characters | `Message must not exceed 200 characters (received 215)` |
| `Hello world` | `Message must include exactly one CTA link (none found)` |
| `Visit https://a.com and www.b.com` | `Message must include exactly one CTA link (found 2: https://a.com, www.b.com)` |
| `Visit www.example.com today` | `CTA link 'www.example.com' must start with http:// or https://` |
| `Visit https://example` | `CTA link 'https://example' must contain a valid domain (e.g. example.com)` |
| `Visit http://localhost:3000` | `CTA link 'http://localhost:3000' must point to a public address` |
| `{"message": "...", "platforms": [...]}` | `Unknown field 'platforms'. Only 'message' is accepted; platform selection is handled internally.` |
| `{}` | `Field 'message' is required` |
| `{not json` | `Request body must be valid JSON` |

Full response bodies:

```text
$ curl -s -X POST localhost:4000/posting -H "Content-Type: application/json" \
    -d '{"message":"Visit https://a.com and https://b.com"}'
HTTP 422
{"success":false,"error":"Validation failed","details":[{"field":"message","message":"Message must include exactly one CTA link (found 2: https://a.com, https://b.com)"}]}

$ curl -s -X POST localhost:4000/posting -H "Content-Type: application/json" \
    -d '{"message":"Hi https://a.com","platforms":["x"]}'
HTTP 422
{"success":false,"error":"Validation failed","details":[{"field":"platforms","message":"Unknown field 'platforms'. Only 'message' is accepted; platform selection is handled internally."}]}
```

## 6. Application log (`logs/app.log`) – isolation of failures

Taken from the automated test that mixes successful, failing, crashing, slow
and unconfigured platforms:

```text
INFO    | posting | Publishing to 6 platform(s): Fake OK, Fake Auth Failure, Fake Crash, Fake Slow, Fake Unconfigured, Fake Private
INFO    | posting | [Fake OK] success -> https://fake.example/post/1 (public=True)
WARNING | posting | [Fake Auth Failure] failed -> Authentication failed (HTTP 401): bad token
ERROR   | posting | Unexpected error while posting to Fake Crash   (traceback logged)
WARNING | posting | [Fake Crash] failed -> Unexpected error: RuntimeError: boom
WARNING | posting | [Fake Unconfigured] failed -> Platform not configured: set TELEGRAM_BOT_TOKEN
INFO    | posting | [Fake Private] success -> https://fake.example/post/1 (public=False)
WARNING | posting | [Fake Slow] failed -> Request timed out
INFO    | posting | Finished: 2 succeeded, 4 failed
```

## 7. Screenshots

Screenshots of the published posts are in [`docs/screenshots/`](screenshots/).

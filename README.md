# Automated Multi-Platform Posting System

A **FastAPI** service that takes one short message and publishes it to
**7 third-party platforms** at once through their official APIs. It returns the
outcome for each platform: status, URL of the post, whether the post is publicly
accessible, date and time, and the error if there was one.

```http
POST http://localhost:4000/posting
{ "message": "Check out our latest business platform and grow your online visibility. https://example.com" }
```

---

## Supported platforms

| # | Platform | Type | API used | Auth | Posted URL | Public |
|---|----------|------|----------|------|-----------|--------|
| 1 | **Telegram** | Messaging channel | [Bot API `sendMessage`](https://core.telegram.org/bots/api#sendmessage) | Bot token | `https://t.me/<channel>/<id>` | Yes, for a public channel |
| 2 | **Discord** | Community chat | [Execute Webhook](https://discord.com/developers/docs/resources/webhook#execute-webhook) (`?wait=true`) | Webhook URL | `https://discord.com/channels/<guild>/<channel>/<id>` | No (server members only) |
| 3 | **Mastodon** | Social network (Fediverse) | [`POST /api/v1/statuses`](https://docs.joinmastodon.org/methods/statuses/#create) | OAuth bearer token | Status URL | Yes (`visibility=public`) |
| 4 | **Bluesky** | Social network (AT Protocol) | [`createSession`](https://docs.bsky.app/docs/get-started#create-a-session) + [`createRecord`](https://docs.bsky.app/docs/advanced-guides/posts) with [link facets](https://docs.bsky.app/docs/advanced-guides/post-richtext) | Handle + app password | `https://bsky.app/profile/<handle>/post/<rkey>` | Yes |
| 5 | **GitHub Gist** | Developer portal | [`POST /gists`](https://docs.github.com/en/rest/gists/gists#create-a-gist) | Personal access token (`gist`) | Gist URL | Yes (`public: true`) |
| 6 | **DEV Community** | Blogging portal (Forem) | [`POST /api/articles`](https://developers.forem.com/api/v1#tag/articles/operation/createArticle) | `api-key` header | Article URL | Yes (`published: true`) |
| 7 | **Hugging Face** | **LLM / AI platform** | [Hub Discussions API](https://huggingface.co/docs/hub/en/repositories-pull-requests-discussions) (`POST /api/{type}s/{repo}/discussions`) | User access token (write) | `https://huggingface.co/<repo>/discussions/<n>` | Yes, if the repo is public |

### Why these platforms
- All seven have **official, documented REST APIs** that can create content
  programmatically with **free** accounts.
- Together they cover social networks, messaging, developer portals, a blogging
  site and an AI/LLM hub, so one message reaches several kinds of audience.
- I left out platforms whose posting APIs need paid tiers or an app review
  before posting (X/Twitter, LinkedIn, Facebook, Instagram).

---

## How it works

```
POST /posting
   │
   ▼
PostingRequest (Pydantic) ── validation ──► 422 {success:false, details:[…]}
   │ valid
   ▼
PostingService.publish()
   │  asyncio.gather (all platforms concurrently, one shared httpx.AsyncClient)
   ├─► Telegram   ─┐
   ├─► Discord     │  each call is isolated:
   ├─► Mastodon    │   • not configured → failed ("Platform not configured: set …")
   ├─► Bluesky     │   • HTTP 4xx/5xx   → failed (platform's own error message)
   ├─► GitHub Gist │   • timeout / network error / unexpected exception → failed
   ├─► DEV         │  one failure never stops the others
   └─► HuggingFace ┘
   │
   ├─ optional anonymous GET of each posted URL → confirms "public_access"
   ├─ history appended to logs/posting_history.jsonl
   ▼
200 {success, summary, results:[…]}
```

* **Platform selection is internal.** The request accepts only `message`.
  Which platforms run is set by the `ENABLED_PLATFORMS` environment variable
  (default `all`). A client that sends a `platforms` field gets a validation error.
* **Public access** comes from the platform's own response (e.g. Mastodon
  `visibility`, Gist `public`, a private HF repo, a Telegram channel without a
  username). With `VERIFY_PUBLIC_ACCESS=true`, the service also sends an
  **unauthenticated** request to the posted URL to confirm it.
* **Date / time** come from the platform's creation timestamp when the API
  returns one, converted to the `TIMEZONE` setting (default `UTC`).

---

## Input validation

| Rule | Example of a rejected message | Error |
|------|------------------------------|-------|
| Not empty | `"   "` | `Message must not be empty` |
| At most 200 characters (after trimming) | 201+ chars | `Message must not exceed 200 characters (received 214)` |
| Exactly one CTA link | `"Hello"` | `Message must include exactly one CTA link (none found)` |
| Exactly one CTA link | `"https://a.com and www.b.com"` | `… (found 2: https://a.com, www.b.com)` |
| Scheme must be http/https | `"Visit www.example.com"` | `CTA link 'www.example.com' must start with http:// or https://` |
| Valid domain and TLD | `https://example`, `https://exa_mple.com` | `… must contain a valid domain` / `… invalid domain name` |
| Public host | `https://localhost`, `https://192.168.1.10` | `… must point to a public address` |
| No embedded credentials | `https://user:pass@example.com` | `… must not contain credentials` |
| Valid port | `https://example.com:99999` | `… is not a valid URL` |
| Only `message` is accepted | `{"message": "...", "platforms": [...]}` | `Unknown field 'platforms' … handled internally` |
| Body must be JSON with a string `message` | `{not json`, `{"message": 1}` | `Request body must be valid JSON` / `Field 'message' must be a string` |

Sentence punctuation after a link is not treated as part of it, so
`https://example.com.` is read as `https://example.com`.

---

## Setup

Requirements: **Python 3.10+**

```bash
git clone <your-repo-url> automated-posting
cd automated-posting

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env        # Windows: copy .env.example .env
# then fill in the credentials of the platforms you want to use
```

### Getting credentials

| Platform | Steps | `.env` keys |
|----------|-------|-------------|
| Telegram | Message [@BotFather](https://t.me/BotFather), send `/newbot`, copy the token. Create a **public** channel, add the bot as an **admin**. | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID=@channelname` |
| Discord | Server Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL | `DISCORD_WEBHOOK_URL` |
| Mastodon | Preferences → Development → New application (scope `write:statuses`) → copy the access token | `MASTODON_INSTANCE_URL`, `MASTODON_ACCESS_TOKEN` |
| Bluesky | Settings → Privacy and security → App passwords → Add | `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` |
| GitHub Gist | Settings → Developer settings → Personal access tokens → token with `gist` scope | `GITHUB_TOKEN` |
| DEV Community | [dev.to/settings/extensions](https://dev.to/settings/extensions) → Generate API key | `DEVTO_API_KEY` |
| Hugging Face | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) → token with **write** access. Create a public repo (model/dataset/space) to post discussions to. | `HF_TOKEN`, `HF_REPO_ID=user/repo`, `HF_REPO_TYPE` |

Platforms without credentials still show up in the response as `failed` with
the message `Platform not configured: set …`. To leave a platform out
completely, list only the platforms you want, e.g.
`ENABLED_PLATFORMS=telegram,mastodon,bluesky,github_gist,devto`.

### Other settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLED_PLATFORMS` | `all` | Comma-separated platform keys |
| `REQUEST_TIMEOUT` | `15` | Seconds per HTTP request |
| `PLATFORM_TIMEOUT` | `30` | Seconds for one platform's whole publish flow |
| `VERIFY_PUBLIC_ACCESS` | `true` | Confirm public access with an anonymous GET |
| `TIMEZONE` | `UTC` | IANA zone for `date` / `time` (e.g. `Asia/Kolkata`) |
| `LOG_LEVEL` / `LOG_DIR` | `INFO` / `logs` | Logging |

---

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

* Swagger UI: <http://localhost:4000/docs>
* ReDoc: <http://localhost:4000/redoc>

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/posting` | **Main endpoint.** Validates the message and publishes it to all enabled platforms |
| `GET` | `/platforms` | Lists supported platforms with their enabled/configured state and missing settings (never shows credential values) |
| `GET` | `/health` | Health check |

---

## Sample requests

**curl**
```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message": "Check out our latest business platform and grow your online visibility. https://example.com"}'
```

**PowerShell**
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:4000/posting `
  -ContentType "application/json" `
  -Body '{"message": "Check out our latest business platform and grow your online visibility. https://example.com"}' |
  ConvertTo-Json -Depth 5
```

**Python**
```python
import httpx
r = httpx.post("http://localhost:4000/posting",
               json={"message": "Check out our latest business platform and grow your online visibility. https://example.com"},
               timeout=60)
print(r.status_code, r.json())
```

## Sample responses

### 200 – processed (some platforms succeeded, others failed)

`success` is `true` when **at least one** platform succeeded. The `summary`
field gives the counts.

```json
{
  "success": true,
  "message": "Check out our latest business platform and grow your online visibility. https://example.com",
  "cta_link": "https://example.com",
  "timezone": "UTC",
  "summary": { "total": 3, "succeeded": 2, "failed": 1 },
  "results": [
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.social/@yourname/113456789012345678",
      "public_access": true,
      "date": "2026-11-15",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Discord",
      "status": "success",
      "posted_url": "https://discord.com/channels/1234/5678/9012",
      "public_access": false,
      "date": "2026-11-15",
      "time": "10:30:01",
      "error": null
    },
    {
      "platform": "GitHub Gist",
      "status": "failed",
      "posted_url": null,
      "public_access": false,
      "date": null,
      "time": null,
      "error": "Authentication failed (HTTP 401): Bad credentials"
    }
  ]
}
```

### 422 – validation error

```json
{
  "success": false,
  "error": "Validation failed",
  "details": [
    {
      "field": "message",
      "message": "Message must include exactly one CTA link (found 2: https://a.com, https://b.com)"
    }
  ]
}
```

Real captured outputs, including live calls to all 7 APIs, are in
[docs/sample_run.md](docs/sample_run.md).

---

## Error handling

| Situation | Result |
|-----------|--------|
| Invalid input | `422` with `{success:false, error, details[]}` |
| Platform credentials missing | that platform → `failed`, `Platform not configured: set …` |
| 401 / 403 | `Authentication failed (HTTP 401): <platform message>` |
| 400 / 422 | `Request rejected (HTTP 400): <platform message>` |
| 404 | `Resource not found (HTTP 404): …` (e.g. an unknown webhook) |
| 429 | `Rate limit exceeded (HTTP 429): …` |
| 5xx | `Platform server error (HTTP 502)` |
| Timeout | `Request timed out` (per-request and per-platform limits) |
| Network failure | `Could not connect to the platform: …` (one automatic retry on connection errors only, so a post is never sent twice) |
| Bug in one integration | caught, logged with traceback, `Unexpected error: …`; the other platforms continue |
| Any other unhandled server error | `500 {success:false, error:"Internal server error"}` |

Logging goes to the console and to `logs/app.log`. Each `/posting` run is also
appended to `logs/posting_history.jsonl`. The `httpx` request log is silenced
because Telegram puts the bot token in the request URL.

---

## Tests

```bash
python -m pytest -q
```

There are 59 tests. No network access or credentials are needed:

* `tests/test_validation.py` – the length, link-count and URL rules, plus edge cases
* `tests/test_posting.py` – the full `/posting` flow with fake platforms: one
  failure does not stop the rest, timeouts, crashes, unconfigured platforms,
  time zones, history file, anonymous public-access check, and every
  validation error format
* `tests/test_platforms.py` – each of the 7 integrations against
  `httpx.MockTransport`: endpoint, auth header, payload, response parsing and
  error mapping. This includes Bluesky's UTF-8 byte offsets for link facets.

---

## Project structure

```text
automated-posting/
├── app/
│   ├── main.py                  # FastAPI app, routes, error handlers, logging
│   ├── schemas.py               # Pydantic request/response models
│   ├── config.py                # Settings from environment / .env
│   ├── validation.py            # Message, link and URL validation
│   ├── platforms/
│   │   ├── __init__.py          # Platform registry and internal selection
│   │   ├── base.py              # BasePlatform, PublishOutcome, error mapping
│   │   ├── telegram.py
│   │   ├── discord.py
│   │   ├── mastodon.py
│   │   ├── bluesky.py
│   │   ├── github_gist.py
│   │   ├── devto.py
│   │   └── huggingface.py
│   └── services/
│       └── posting_service.py   # Concurrent, isolated publishing
├── tests/
│   ├── conftest.py
│   ├── test_validation.py
│   ├── test_posting.py
│   └── test_platforms.py
├── docs/
│   └── sample_run.md            # Captured logs and responses
├── .env.example
├── requirements.txt
├── pytest.ini
└── README.md
```

### Adding a new platform

1. Create `app/platforms/<name>.py` with a subclass of `BasePlatform`. Set
   `key`, `name`, `docs_url` and `required_settings`, and implement
   `publish()` so it returns a `PublishOutcome`.
2. Add its settings to `app/config.py` and `.env.example`.
3. Register the class in `PLATFORM_CLASSES` in `app/platforms/__init__.py`.

---

## Security

* All credentials are read from environment variables or `.env`. The `.env`
  file is listed in `.gitignore`, and only `.env.example` (with empty values)
  is committed.
* `/platforms` returns only the **names** of missing settings, never their values.
* Error messages come from the platforms' response bodies. Request URLs and
  headers that contain tokens are never logged or returned.

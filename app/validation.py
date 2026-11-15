"""Message and CTA-link validation helpers.

Rules (from the specification):
  * the message must not exceed 200 characters;
  * it must contain exactly one CTA link;
  * that link must be a valid URL.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

MAX_MESSAGE_LENGTH = 200

# Anything that *looks* like a link counts towards the "exactly one link" rule,
# including links without a scheme (``www.example.com``), so that they cannot
# be used to sneak a second link past the validator.
LINK_PATTERN = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'`]+")

_TRAILING_PUNCTUATION = ".,;:!?'\""
_BRACKETS = {")": "(", "]": "[", "}": "{"}

_DOMAIN_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$", re.IGNORECASE)
_TLD = re.compile(r"^(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})$", re.IGNORECASE)


def _trim_link(candidate: str) -> str:
    """Strip punctuation that ends a sentence rather than the URL itself."""
    while candidate:
        last = candidate[-1]
        if last in _TRAILING_PUNCTUATION:
            candidate = candidate[:-1]
        elif last in _BRACKETS and candidate.count(last) > candidate.count(_BRACKETS[last]):
            candidate = candidate[:-1]
        else:
            break
    return candidate


def extract_links(message: str) -> list[str]:
    """Return every link-like token found in the message."""
    return [_trim_link(match.group(0)) for match in LINK_PATTERN.finditer(message)]


def validate_url(url: str) -> str:
    """Validate a CTA URL and return it unchanged. Raises ``ValueError``."""
    if not re.match(r"(?i)^https?://", url):
        raise ValueError(f"CTA link '{url}' must start with http:// or https://")

    try:
        parts = urlsplit(url)
        port = parts.port  # raises ValueError for an invalid port
    except ValueError as exc:
        raise ValueError(f"CTA link '{url}' is not a valid URL: {exc}") from None

    if parts.username or parts.password:
        raise ValueError(f"CTA link '{url}' must not contain credentials")

    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise ValueError(f"CTA link '{url}' is missing a host name")
    if port == 0:
        raise ValueError(f"CTA link '{url}' has an invalid port")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None:
        if not ip.is_global:
            raise ValueError(f"CTA link '{url}' must point to a public address")
        return url

    if host.lower() == "localhost":
        raise ValueError(f"CTA link '{url}' must point to a public address")

    labels = host.split(".")
    if len(labels) < 2 or len(host) > 253:
        raise ValueError(f"CTA link '{url}' must contain a valid domain (e.g. example.com)")
    if not all(_DOMAIN_LABEL.match(label) for label in labels):
        raise ValueError(f"CTA link '{url}' contains an invalid domain name '{host}'")
    if not _TLD.match(labels[-1]):
        raise ValueError(f"CTA link '{url}' has an invalid top-level domain '.{labels[-1]}'")

    return url


def validate_message(message: str) -> tuple[str, str]:
    """Validate a message and return ``(clean_message, cta_link)``.

    Raises ``ValueError`` with a human readable explanation on failure.
    """
    cleaned = message.strip()
    if not cleaned:
        raise ValueError("Message must not be empty")
    if len(cleaned) > MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message must not exceed {MAX_MESSAGE_LENGTH} characters "
            f"(received {len(cleaned)})"
        )

    links = extract_links(cleaned)
    if not links:
        raise ValueError("Message must include exactly one CTA link (none found)")
    if len(links) > 1:
        raise ValueError(
            f"Message must include exactly one CTA link (found {len(links)}: {', '.join(links)})"
        )

    link = validate_url(links[0])
    return cleaned, link


def message_without_link(message: str, link: str) -> str:
    """The message text with the CTA link removed (used for titles)."""
    text = message.replace(link, " ")
    return re.sub(r"\s+", " ", text).strip(" -:|")


def make_title(message: str, link: str, max_length: int = 80) -> str:
    """Build a short, human readable title out of the message text."""
    text = message_without_link(message, link) or "New update"
    first_sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    title = first_sentence.rstrip(".") or text
    if len(title) > max_length:
        title = title[: max_length - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return title

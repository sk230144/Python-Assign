import pytest

from app.validation import extract_links, make_title, validate_message, validate_url


def test_valid_message_returns_link():
    message, link = validate_message(
        "  Check out our latest business platform. https://example.com  "
    )
    assert message == "Check out our latest business platform. https://example.com"
    assert link == "https://example.com"


def test_message_at_exact_limit_is_accepted():
    link = " https://example.com"
    message = "a" * (200 - len(link)) + link
    assert len(message) == 200
    validate_message(message)


def test_message_over_limit_is_rejected():
    message = "a" * 190 + " https://example.com"
    with pytest.raises(ValueError, match="must not exceed 200 characters"):
        validate_message(message)


@pytest.mark.parametrize("message", ["", "   "])
def test_empty_message_is_rejected(message):
    with pytest.raises(ValueError, match="must not be empty"):
        validate_message(message)


def test_message_without_link_is_rejected():
    with pytest.raises(ValueError, match="none found"):
        validate_message("No link in this message at all")


def test_message_with_two_links_is_rejected():
    with pytest.raises(ValueError, match="found 2"):
        validate_message("Visit https://a.com and https://b.com")


def test_scheme_less_link_counts_as_second_link():
    with pytest.raises(ValueError, match="found 2"):
        validate_message("Visit https://a.com or www.b.com")


def test_scheme_less_single_link_is_rejected():
    with pytest.raises(ValueError, match="must start with http"):
        validate_message("Visit www.example.com today")


def test_trailing_punctuation_is_not_part_of_link():
    assert extract_links("Go to https://example.com/page.") == ["https://example.com/page"]
    assert extract_links("(see https://example.com)") == ["https://example.com"]
    assert extract_links("wiki https://en.wikipedia.org/wiki/Foo_(bar)") == [
        "https://en.wikipedia.org/wiki/Foo_(bar)"
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://sub.example.co.uk/path?x=1#top",
        "https://example.com:8443/a",
        "https://8.8.8.8/",
    ],
)
def test_valid_urls(url):
    assert validate_url(url) == url


@pytest.mark.parametrize(
    "url, reason",
    [
        ("ftp://example.com", "must start with http"),
        ("https://localhost/page", "public address"),
        ("https://127.0.0.1/", "public address"),
        ("https://192.168.1.10/", "public address"),
        ("https://example", "valid domain"),
        ("https://exa_mple.com", "invalid domain"),
        ("https://-bad.com", "invalid domain"),
        ("https://example.c0m", "top-level domain"),
        ("https://user:pass@example.com", "credentials"),
        ("https://example.com:99999", "not a valid URL"),
        ("https://", "missing a host"),
    ],
)
def test_invalid_urls(url, reason):
    with pytest.raises(ValueError, match=reason):
        validate_url(url)


def test_make_title_strips_link_and_uses_first_sentence():
    message = "Grow your online visibility. Join now! https://example.com"
    assert make_title(message, "https://example.com") == "Grow your online visibility"


def test_make_title_falls_back_when_only_link():
    assert make_title("https://example.com", "https://example.com") == "New update"

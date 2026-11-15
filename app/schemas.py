"""Pydantic request / response models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.validation import MAX_MESSAGE_LENGTH, extract_links, validate_message


class PostingRequest(BaseModel):
    """Body of ``POST /posting``.

    Only ``message`` is accepted: platform selection is handled internally,
    so any extra field (for example ``platforms``) is rejected.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "message": "Check out our latest business platform and grow your "
                    "online visibility. https://example.com"
                }
            ]
        },
    )

    message: str = Field(
        ...,
        description=f"Message to publish (max {MAX_MESSAGE_LENGTH} characters, "
        "exactly one http(s) CTA link).",
    )

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        cleaned, _ = validate_message(value)
        return cleaned

    @property
    def link(self) -> str:
        """The single, already validated CTA link contained in the message."""
        return extract_links(self.message)[0]


class PostStatus(str, Enum):
    success = "success"
    failed = "failed"


class PlatformResult(BaseModel):
    platform: str = Field(..., examples=["Mastodon"])
    status: PostStatus
    posted_url: str | None = Field(None, examples=["https://mastodon.social/@user/1"])
    public_access: bool = False
    date: str | None = Field(None, examples=["2026-11-15"])
    time: str | None = Field(None, examples=["10:30:00"])
    error: str | None = None


class PostingSummary(BaseModel):
    total: int
    succeeded: int
    failed: int


class PostingResponse(BaseModel):
    success: bool = Field(..., description="True when at least one platform succeeded.")
    message: str
    cta_link: str
    timezone: str
    summary: PostingSummary
    results: list[PlatformResult]


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    details: list[ValidationErrorDetail] = []


class PlatformInfo(BaseModel):
    key: str
    name: str
    enabled: bool
    configured: bool
    missing_settings: list[str]
    docs_url: str

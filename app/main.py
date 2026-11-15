"""FastAPI entry point.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 4000
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.platforms import get_all_platforms, is_enabled
from app.schemas import (
    ErrorResponse,
    PlatformInfo,
    PostingRequest,
    PostingResponse,
    ValidationErrorDetail,
)
from app.services.posting_service import PostingService


# ---------------------------------------------------------------------- #
# Logging
# ---------------------------------------------------------------------- #
def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    if getattr(root, "_posting_configured", False):
        return
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    root.setLevel(settings.log_level.upper())

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        root.warning("File logging disabled: cannot write to %s", settings.log_dir)

    # Never log request URLs that may embed secrets (e.g. Telegram bot token).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    root._posting_configured = True  # type: ignore[attr-defined]


settings = get_settings()
configure_logging(settings)
logger = logging.getLogger("app")

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Publishes a short message (max 200 characters, exactly one CTA link) "
        "to multiple third-party platforms at once: Telegram, Discord, Mastodon, "
        "Bluesky, GitHub Gist, DEV Community and Hugging Face."
    ),
)


# ---------------------------------------------------------------------- #
# Error handling
# ---------------------------------------------------------------------- #
def _describe_validation_error(error: dict) -> ValidationErrorDetail:
    loc = [str(part) for part in error.get("loc", ()) if part != "body"]
    field = ".".join(loc) or "body"
    err_type = error.get("type", "")
    message = str(error.get("msg", "Invalid value"))

    if err_type == "value_error":
        message = message.removeprefix("Value error, ")
    elif err_type == "extra_forbidden":
        message = (
            f"Unknown field '{field}'. Only 'message' is accepted; "
            "platform selection is handled internally."
        )
    elif err_type == "missing":
        message = "Request body is required" if field == "body" else f"Field '{field}' is required"
    elif err_type == "json_invalid":
        field, message = "body", "Request body must be valid JSON"
    elif err_type == "string_type":
        message = f"Field '{field}' must be a string"
    elif err_type == "model_attributes_type":
        message = "Request body must be a JSON object"
    return ValidationErrorDetail(field=field, message=message)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [_describe_validation_error(err) for err in exc.errors()]
    logger.info("Validation failed: %s", "; ".join(d.message for d in details))
    body = ErrorResponse(error="Validation failed", details=details)
    return JSONResponse(status_code=422, content=body.model_dump())


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    body = ErrorResponse(error=str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(), headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    body = ErrorResponse(error="Internal server error")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body.model_dump())


# ---------------------------------------------------------------------- #
# Dependencies
# ---------------------------------------------------------------------- #
def get_posting_service() -> PostingService:
    return PostingService(get_settings())


# ---------------------------------------------------------------------- #
# Routes
# ---------------------------------------------------------------------- #
@app.post(
    "/posting",
    response_model=PostingResponse,
    tags=["Posting"],
    summary="Publish a message to all enabled platforms",
    responses={
        422: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
)
async def create_posting(
    payload: PostingRequest,
    service: PostingService = Depends(get_posting_service),
) -> PostingResponse:
    """Publish `message` to every enabled platform concurrently.

    Each platform is handled independently: if one fails, the others are
    still attempted, and the per-platform outcome is returned in `results`.
    """
    return await service.publish(payload.message, payload.link)


@app.get("/platforms", response_model=list[PlatformInfo], tags=["Platforms"])
async def list_platforms() -> list[PlatformInfo]:
    """Supported platforms and whether each one is enabled / configured
    (credential values are never returned)."""
    current = get_settings()
    return [
        PlatformInfo(
            key=p.key,
            name=p.name,
            enabled=is_enabled(p.key, current),
            configured=p.is_configured(),
            missing_settings=p.missing_settings(),
            docs_url=p.docs_url,
        )
        for p in get_all_platforms(current)
    ]


@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")

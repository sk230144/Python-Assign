from __future__ import annotations

import os
import tempfile

# Keep test runs out of the real logs/ folder and ignore any local .env.
os.environ.setdefault("LOG_DIR", tempfile.mkdtemp(prefix="posting-tests-"))

import pytest
from fastapi.testclient import TestClient

from app.config import Settings  # noqa: E402
from app.main import app  # noqa: E402


def make_settings(tmp_path, **overrides) -> Settings:
    """Settings isolated from the developer's real .env file."""
    base = {"log_dir": str(tmp_path / "logs"), "verify_public_access": False}
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

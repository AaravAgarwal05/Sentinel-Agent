"""Tests for the runtime settings module."""

from __future__ import annotations

import pydantic
import pytest

from agent.config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests."""
    get_settings.cache_clear()


def test_settings_load_with_defaults() -> None:
    """Settings load with the documented defaults."""
    settings = Settings()
    assert settings.agent_name == "sentinel-agent"
    assert settings.agent_version == "0.1.0"
    assert settings.environment == "development"
    assert settings.log_level == "INFO"


def test_get_settings_returns_settings_instance() -> None:
    """``get_settings`` returns a ``Settings`` instance."""
    assert isinstance(get_settings(), Settings)


def test_settings_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables prefixed with ``SENTINEL_`` override defaults."""
    monkeypatch.setenv("SENTINEL_AGENT_NAME", "test-agent")
    monkeypatch.setenv("SENTINEL_ENVIRONMENT", "testing")
    settings = Settings()
    assert settings.agent_name == "test-agent"
    assert settings.environment == "testing"


def test_settings_invalid_log_level_rejected() -> None:
    """Log levels outside the allowed Literal set are rejected."""
    with pytest.raises(pydantic.ValidationError):
        Settings(log_level="VERBOSE")  # type: ignore[arg-type]

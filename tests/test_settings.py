"""Tests for the hierarchical settings module."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.config.settings import (
    AgentConfig,
    HeartbeatConfig,
    RuntimeConfig,
    SentinelConfig,
    Settings,
    StorageConfig,
    get_settings,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests."""
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------


def test_settings_load_with_defaults() -> None:
    """Settings load with the documented defaults across all four domains."""
    settings = Settings()
    assert settings.agent.name == "sentinel-agent"
    assert settings.agent.version == "0.1.0"
    assert settings.agent.cluster_name == "default"
    assert settings.agent.environment == "development"
    assert settings.sentinel.api_url == "https://api.sentinel.example.com"
    assert settings.sentinel.registration_token == ""
    assert settings.heartbeat.interval_seconds == 30
    assert settings.runtime.log_level == "INFO"
    assert settings.storage.database_url == "sqlite:////data/sentinel_agent.db"


def test_get_settings_returns_settings_instance() -> None:
    """``get_settings`` returns a ``Settings`` instance."""
    assert isinstance(get_settings(), Settings)


def test_get_settings_is_cached() -> None:
    """``get_settings`` returns the same instance on repeated calls."""
    assert get_settings() is get_settings()


def test_nested_configs_are_correct_types() -> None:
    """Each domain is exposed as its declared Pydantic model."""
    settings = Settings()
    assert isinstance(settings.agent, AgentConfig)
    assert isinstance(settings.sentinel, SentinelConfig)
    assert isinstance(settings.heartbeat, HeartbeatConfig)
    assert isinstance(settings.runtime, RuntimeConfig)
    assert isinstance(settings.storage, StorageConfig)


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


def test_agent_name_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_AGENT_NAME", "my-agent")
    settings = Settings()
    assert settings.agent.name == "my-agent"


def test_agent_version_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_AGENT_VERSION", "1.2.3")
    settings = Settings()
    assert settings.agent.version == "1.2.3"


def test_agent_cluster_name_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_AGENT_CLUSTER_NAME", "prod-cluster-1")
    settings = Settings()
    assert settings.agent.cluster_name == "prod-cluster-1"


def test_agent_environment_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_AGENT_ENVIRONMENT", "production")
    settings = Settings()
    assert settings.agent.environment == "production"


def test_sentinel_api_url_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_SENTINEL_API_URL", "https://api.example.com")
    settings = Settings()
    assert settings.sentinel.api_url == "https://api.example.com"


def test_sentinel_registration_token_override_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTINEL_SENTINEL_REGISTRATION_TOKEN", "secret-token")
    settings = Settings()
    assert settings.sentinel.registration_token == "secret-token"


def test_heartbeat_interval_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_HEARTBEAT_INTERVAL_SECONDS", "60")
    settings = Settings()
    assert settings.heartbeat.interval_seconds == 60


def test_runtime_log_level_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_RUNTIME_LOG_LEVEL", "DEBUG")
    settings = Settings()
    assert settings.runtime.log_level == "DEBUG"


def test_storage_database_url_override_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SENTINEL_STORAGE_DATABASE_URL`` populates ``settings.storage.database_url``."""
    monkeypatch.setenv("SENTINEL_STORAGE_DATABASE_URL", "sqlite:///:memory:")
    settings = Settings()
    assert settings.storage.database_url == "sqlite:///:memory:"


def test_env_vars_override_all_domains_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full set of env vars produces the expected full settings tree."""
    monkeypatch.setenv("SENTINEL_AGENT_NAME", "cluster-agent")
    monkeypatch.setenv("SENTINEL_AGENT_CLUSTER_NAME", "staging-cluster")
    monkeypatch.setenv("SENTINEL_SENTINEL_API_URL", "https://api.staging.example.com")
    monkeypatch.setenv("SENTINEL_HEARTBEAT_INTERVAL_SECONDS", "15")
    settings = Settings()
    assert settings.agent.name == "cluster-agent"
    assert settings.agent.cluster_name == "staging-cluster"
    assert settings.sentinel.api_url == "https://api.staging.example.com"
    assert settings.heartbeat.interval_seconds == 15


def test_unknown_env_var_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown ``SENTINEL_*`` env vars are ignored without error."""
    monkeypatch.setenv("SENTINEL_UNKNOWN_DOMAIN_FIELD", "ignored")
    settings = Settings()
    assert settings.agent.name == "sentinel-agent"


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


def test_heartbeat_interval_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        HeartbeatConfig(interval_seconds=0)


def test_heartbeat_interval_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        HeartbeatConfig(interval_seconds=-1)


def test_api_url_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        SentinelConfig(api_url="")


def test_invalid_environment_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentConfig(environment="testing")  # type: ignore[arg-type]


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig(log_level="VERBOSE")  # type: ignore[arg-type]


def test_invalid_heartbeat_interval_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``SENTINEL_HEARTBEAT_INTERVAL_SECONDS=0`` is rejected at validation time."""
    monkeypatch.setenv("SENTINEL_HEARTBEAT_INTERVAL_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_environment_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown environment value from env is rejected at validation time."""
    monkeypatch.setenv("SENTINEL_AGENT_ENVIRONMENT", "qa")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_log_level_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown log level from env is rejected at validation time."""
    monkeypatch.setenv("SENTINEL_RUNTIME_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError):
        Settings()


# ---------------------------------------------------------------------------
# Nested settings access
# ---------------------------------------------------------------------------


def test_nested_field_access() -> None:
    """Nested access works the same regardless of how settings were loaded."""
    settings = Settings(
        agent=AgentConfig(
            name="nested",
            version="2.0.0",
            cluster_name="nested-cluster",
            environment="staging",
        ),
        sentinel=SentinelConfig(
            api_url="https://api.nested.example.com",
            registration_token="nested-token",
        ),
        heartbeat=HeartbeatConfig(interval_seconds=45),
        runtime=RuntimeConfig(log_level="WARNING"),
    )
    assert settings.agent.name == "nested"
    assert settings.agent.version == "2.0.0"
    assert settings.agent.cluster_name == "nested-cluster"
    assert settings.agent.environment == "staging"
    assert settings.sentinel.api_url == "https://api.nested.example.com"
    assert settings.sentinel.registration_token == "nested-token"
    assert settings.heartbeat.interval_seconds == 45
    assert settings.runtime.log_level == "WARNING"

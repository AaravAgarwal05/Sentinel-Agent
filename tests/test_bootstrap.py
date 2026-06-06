"""Tests for the runtime bootstrap manager."""

from __future__ import annotations

import json

import pytest

from agent.config.settings import (
    AgentConfig,
    RuntimeConfig,
    Settings,
    get_settings,
)
from agent.runtime.bootstrap import BootstrapManager


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests."""
    get_settings.cache_clear()


def test_bootstrap_manager_creates_with_defaults() -> None:
    """``BootstrapManager`` can be constructed without arguments."""
    bootstrap = BootstrapManager()
    assert bootstrap is not None


def test_bootstrap_manager_accepts_settings() -> None:
    """``BootstrapManager`` accepts an explicit ``Settings`` instance."""
    bootstrap = BootstrapManager(settings=Settings(agent=AgentConfig(name="custom")))
    assert bootstrap is not None


def test_bootstrap_manager_start_emits_startup_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``start()`` configures logging and emits the startup event as JSON to stdout."""
    bootstrap = BootstrapManager(
        settings=Settings(
            agent=AgentConfig(
                name="test-agent",
                version="9.9.9",
                environment="staging",
                cluster_name="test-cluster",
            ),
            runtime=RuntimeConfig(log_level="INFO"),
        )
    )
    bootstrap.start()
    out = capsys.readouterr().out

    events = [
        json.loads(line)
        for line in out.splitlines()
        if line.strip().startswith("{")
    ]
    startup = [
        event for event in events if event.get("event") == "Sentinel Agent starting"
    ]
    assert len(startup) == 1
    event = startup[0]
    assert event["level"] == "info"
    assert event["logger"] == "agent.runtime.bootstrap"
    assert event["agent_name"] == "test-agent"
    assert event["agent_version"] == "9.9.9"
    assert event["environment"] == "staging"
    assert event["log_level"] == "INFO"
    assert event["cluster_name"] == "test-cluster"
    assert "timestamp" in event


def test_bootstrap_manager_start_runs_without_error() -> None:
    """``start()`` is idempotent and safe to invoke once per process."""
    BootstrapManager(settings=Settings(agent=AgentConfig(name="idempotent"))).start()


def test_bootstrap_manager_reads_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The startup log reflects values loaded from the environment."""
    monkeypatch.setenv("SENTINEL_AGENT_NAME", "env-agent")
    monkeypatch.setenv("SENTINEL_AGENT_VERSION", "3.0.0")
    monkeypatch.setenv("SENTINEL_AGENT_ENVIRONMENT", "production")
    monkeypatch.setenv("SENTINEL_AGENT_CLUSTER_NAME", "env-cluster")
    monkeypatch.setenv("SENTINEL_RUNTIME_LOG_LEVEL", "DEBUG")

    bootstrap = BootstrapManager()
    bootstrap.start()

    out = capsys.readouterr().out
    events = [
        json.loads(line)
        for line in out.splitlines()
        if line.strip().startswith("{")
    ]
    startup = [
        event for event in events if event.get("event") == "Sentinel Agent starting"
    ]
    assert len(startup) == 1
    event = startup[0]
    assert event["agent_name"] == "env-agent"
    assert event["agent_version"] == "3.0.0"
    assert event["environment"] == "production"
    assert event["cluster_name"] == "env-cluster"
    assert event["log_level"] == "DEBUG"

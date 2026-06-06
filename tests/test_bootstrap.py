"""Tests for the runtime bootstrap manager."""

from __future__ import annotations

import json

import pytest

from agent.config.settings import Settings
from agent.runtime.bootstrap import BootstrapManager


def test_bootstrap_manager_creates_with_defaults() -> None:
    """``BootstrapManager`` can be constructed without arguments."""
    bootstrap = BootstrapManager()
    assert bootstrap is not None


def test_bootstrap_manager_accepts_settings() -> None:
    """``BootstrapManager`` accepts an explicit ``Settings`` instance."""
    bootstrap = BootstrapManager(settings=Settings(agent_name="custom"))
    assert bootstrap is not None


def test_bootstrap_manager_start_emits_startup_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``start()`` configures logging and emits the startup event as JSON to stdout."""
    bootstrap = BootstrapManager(
        settings=Settings(
            agent_name="test-agent",
            agent_version="9.9.9",
            environment="testing",
            log_level="INFO",
        )
    )
    bootstrap.start()
    out = capsys.readouterr().out

    events = [
        json.loads(line)
        for line in out.splitlines()
        if line.strip().startswith("{")
    ]
    startup = [event for event in events if event.get("event") == "Sentinel Agent starting"]
    assert len(startup) == 1
    event = startup[0]
    assert event["level"] == "info"
    assert event["logger"] == "agent.runtime.bootstrap"
    assert event["agent_name"] == "test-agent"
    assert event["agent_version"] == "9.9.9"
    assert event["environment"] == "testing"
    assert "timestamp" in event


def test_bootstrap_manager_start_runs_without_error() -> None:
    """``start()`` is idempotent and safe to invoke once per process."""
    BootstrapManager(settings=Settings(agent_name="idempotent")).start()

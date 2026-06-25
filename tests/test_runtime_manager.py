"""Tests for the runtime lifecycle manager."""
from __future__ import annotations

import signal
from unittest.mock import MagicMock, patch

import pytest

from agent.config.settings import Settings, get_settings
from agent.heartbeat.scheduler import HeartbeatScheduler
from agent.runtime.runtime_manager import RuntimeManager


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests."""
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_runtime_manager_construction_with_default_settings() -> None:
    """``RuntimeManager`` can be constructed without arguments and uses
    the process-wide settings singleton."""
    mgr = RuntimeManager()
    assert mgr is not None
    assert mgr.started is False

    default_settings = get_settings()
    assert mgr._settings.agent.name == default_settings.agent.name


def test_runtime_manager_construction_with_explicit_settings() -> None:
    """``RuntimeManager`` accepts an explicit ``Settings`` instance."""
    settings = Settings()
    mgr = RuntimeManager(settings=settings)
    assert mgr._settings is settings
    assert mgr.started is False


# ---------------------------------------------------------------------------
# Startup lifecycle
# ---------------------------------------------------------------------------


def _mock_bootstrap() -> MagicMock:
    """Return a MagicMock that can be used as a BootstrapManager."""
    return MagicMock()


def _mock_database() -> MagicMock:
    """Return a MagicMock for DatabaseManager that supports ``session()``."""
    db = MagicMock()
    db.session.return_value.__enter__.return_value = MagicMock()
    return db


def test_start_completes_full_startup_sequence() -> None:
    """``start()`` completes the full startup sequence successfully."""
    mock_bootstrap_cls = MagicMock(return_value=MagicMock())

    with patch("agent.runtime.runtime_manager.BootstrapManager",
               mock_bootstrap_cls):
        with patch("agent.runtime.runtime_manager.DatabaseManager",
                   return_value=_mock_database()):
            with patch("agent.runtime.runtime_manager.KubernetesClient",
                       return_value=MagicMock(available=False)):
                with patch("agent.runtime.runtime_manager.RegistrationService") \
                        as mock_reg_cls:
                    mock_reg_instance = MagicMock()
                    mock_reg_instance.register.return_value = MagicMock(
                        agent_id="test-agent",
                        api_key="test-key",
                        api_url="https://api.example.com",
                        expires_at=None,
                        cluster_id="test-cluster",
                    )
                    mock_reg_cls.return_value = mock_reg_instance

                    mgr = RuntimeManager()
                    mgr.start()

                    assert mgr.started is True
                    mock_reg_instance.register.assert_called_once()


def test_start_handles_registration_failure_gracefully() -> None:
    """``start()`` continues when ``RegistrationService.register()``
    returns ``None``."""
    with patch("agent.runtime.runtime_manager.BootstrapManager",
               return_value=MagicMock()):
        with patch("agent.runtime.runtime_manager.DatabaseManager",
                   return_value=_mock_database()):
            with patch("agent.runtime.runtime_manager.KubernetesClient",
                       return_value=MagicMock(available=False)):
                with patch("agent.runtime.runtime_manager.RegistrationService") \
                        as mock_reg_cls:
                    mock_reg_instance = MagicMock()
                    mock_reg_instance.register.return_value = None
                    mock_reg_cls.return_value = mock_reg_instance

                    mgr = RuntimeManager()
                    mgr.start()

                    assert mgr.started is True
                    mock_reg_instance.register.assert_called_once()


# ---------------------------------------------------------------------------
# Shutdown lifecycle
# ---------------------------------------------------------------------------


def test_stop_is_idempotent_when_not_started() -> None:
    """Calling ``stop()`` on a manager that was never started is safe."""
    mgr = RuntimeManager()
    mgr.stop()  # Should not raise
    assert mgr.started is False


def test_stop_gracefully_stops_heartbeat_scheduler() -> None:
    """``stop()`` stops the heartbeat scheduler when it is running."""
    mock_scheduler = MagicMock(spec=HeartbeatScheduler)
    mock_scheduler.running = True

    mgr = RuntimeManager()
    mgr._started = True
    mgr._heartbeat_scheduler = mock_scheduler
    mgr.stop()

    assert mgr.started is False
    mock_scheduler.stop.assert_called_once()


def test_stop_skips_scheduler_when_not_running() -> None:
    """``stop()`` does not call ``scheduler.stop()`` if the scheduler was
    never started or already stopped."""
    mock_scheduler = MagicMock(spec=HeartbeatScheduler)
    mock_scheduler.running = False

    mgr = RuntimeManager()
    mgr._started = True
    mgr._heartbeat_scheduler = mock_scheduler
    mgr.stop()

    mock_scheduler.stop.assert_not_called()


def test_stop_skips_scheduler_when_none() -> None:
    """``stop()`` handles the case where registration failed and no
    scheduler was created."""
    mgr = RuntimeManager()
    mgr._started = True
    mgr._heartbeat_scheduler = None
    mgr.stop()  # Should not raise or attempt to call .stop() on None

    assert mgr.started is False


def test_wait_registers_signal_handlers() -> None:
    """``wait()`` registers handlers for ``SIGTERM`` and ``SIGINT``."""
    mgr = RuntimeManager()

    with patch("signal.signal") as mock_signal:
        # Set the event immediately so wait() returns (no real blocking)
        mgr._shutdown_event.set()
        mgr.wait()

        # Verify signal handlers were registered
        sigterm_call = any(
            c.args[0] == signal.SIGTERM for c in mock_signal.call_args_list
        )
        sigint_call = any(
            c.args[0] == signal.SIGINT for c in mock_signal.call_args_list
        )
        assert sigterm_call, "SIGTERM handler not registered"
        assert sigint_call, "SIGINT handler not registered"


def test_signal_handler_triggers_shutdown_event() -> None:
    """``_signal_handler()`` sets the shutdown event, causing ``wait()``
    to return."""
    mgr = RuntimeManager()
    assert mgr._shutdown_event.is_set() is False

    mgr._signal_handler(signal.SIGTERM, None)

    assert mgr._shutdown_event.is_set() is True


def test_full_lifecycle_start_wait_stop() -> None:
    """Simulates the full lifecycle: start, wait for signal, stop.

    Verifies that ``stop()`` cleans up the scheduler and marks the
    manager as not started.
    """
    mock_scheduler = MagicMock(spec=HeartbeatScheduler)
    mock_scheduler.running = True

    mgr = RuntimeManager()

    # Manually simulate what start() would set up
    mgr._started = True
    mgr._heartbeat_scheduler = mock_scheduler

    # Simulate signal arriving
    mgr._signal_handler(signal.SIGTERM, None)

    # This is what main() does after wait() returns
    mgr.stop()

    assert mgr.started is False
    mock_scheduler.stop.assert_called_once()


def test_started_property_after_start() -> None:
    """``started`` is ``True`` after ``start()`` completes."""
    with patch("agent.runtime.runtime_manager.BootstrapManager",
               return_value=MagicMock()):
        with patch("agent.runtime.runtime_manager.DatabaseManager",
                   return_value=_mock_database()):
            with patch("agent.runtime.runtime_manager.KubernetesClient",
                       return_value=MagicMock(available=False)):
                with patch("agent.runtime.runtime_manager.RegistrationService") \
                        as mock_reg_cls:
                    mock_reg_instance = MagicMock()
                    mock_reg_instance.register.return_value = MagicMock(
                        agent_id="test-agent",
                        api_key="test-key",
                        api_url="https://api.example.com",
                        expires_at=None,
                        cluster_id="test-cluster",
                    )
                    mock_reg_cls.return_value = mock_reg_instance

                    mgr = RuntimeManager()
                    mgr.start()

                    assert mgr.started is True

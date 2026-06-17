"""Tests for the runtime lifecycle manager."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.config.settings import Settings, get_settings
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

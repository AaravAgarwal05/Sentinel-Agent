"""Runtime bootstrap for the Sentinel Agent."""

from __future__ import annotations

from agent.common.logging import configure_logging, get_logger
from agent.config.settings import Settings, get_settings

_STARTUP_LOGGER = "agent.runtime.bootstrap"


class BootstrapManager:
    """Initializes logging, loads settings, and emits startup events.

    This is the only lifecycle component active in Phase 1. Future
    phases will register additional managers on top of this skeleton,
    but the bootstrap manager itself is intentionally minimal.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings: Settings = settings if settings is not None else get_settings()

    def start(self) -> None:
        """Configure logging and emit the startup event."""
        configure_logging(log_level=self._settings.runtime.log_level)
        logger = get_logger(_STARTUP_LOGGER)
        logger.info(
            "Sentinel Agent starting",
            agent_name=self._settings.agent.name,
            agent_version=self._settings.agent.version,
            environment=self._settings.agent.environment,
            log_level=self._settings.runtime.log_level,
            cluster_name=self._settings.agent.cluster_name,
        )

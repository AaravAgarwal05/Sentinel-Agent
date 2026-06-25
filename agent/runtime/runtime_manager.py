"""Runtime lifecycle manager for the Sentinel Agent."""

from __future__ import annotations

import signal
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType

from agent.auth.manager import CredentialsManager
from agent.collection import (
    models as collection_models,  # noqa: F401 — registers IncidentContext in Base.metadata for create_all
)
from agent.common.kubernetes import KubernetesClient
from agent.common.logging import get_logger
from agent.config.settings import Settings, get_settings
from agent.detection.service import DetectionService
from agent.diagnostics import (
    models as diagnostics_models,  # noqa: F401 — registers DiagnosticReport in Base.metadata for create_all
)
from agent.heartbeat.scheduler import HeartbeatScheduler
from agent.registration.service import RegistrationService
from agent.runtime.bootstrap import BootstrapManager
from agent.storage.database import DatabaseManager
from agent.storage.models import Base
from agent.transport import (
    models as transport_models,  # noqa: F401 — registers OutboundReport in Base.metadata for create_all
)
from agent.transport.retry import RetryService

_MARKER_PATH = Path("/tmp/sentinel-agent-ready")


class RuntimeManager:
    """Orchestrates the full agent startup sequence.

    Flow:
    1. BootstrapManager.start() -- logging + startup event
    2. DatabaseManager.initialize() -- SQLAlchemy engine + session factory
    3. KubernetesClient -- cluster metadata (graceful if unavailable)
    4. RegistrationService.register() -- register with SentinelAI
    5. CredentialsManager.store_credentials() -- persist auth
    6. HeartbeatScheduler.start() -- begin periodic heartbeats
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Store an optional settings override; default singleton otherwise.

        Args:
            settings: Optional pre-built settings instance. When ``None`` the
                process-wide :func:`get_settings` singleton is used.
        """
        self._settings: Settings = settings or get_settings()
        self._db: DatabaseManager | None = None
        self._k8s_client: KubernetesClient | None = None
        self._registration_service: RegistrationService | None = None
        self._credentials_manager: CredentialsManager | None = None
        self._heartbeat_scheduler: HeartbeatScheduler | None = None
        self._detection_service: DetectionService | None = None
        self._retry_service: RetryService | None = None
        self._started: bool = False
        self._shutdown_event: threading.Event = threading.Event()

    def start(self) -> None:
        """Execute the full startup sequence.

        Step-by-step with logging at each stage. If registration fails
        (mock or real), the agent still starts but logs a warning.
        The heartbeat scheduler starts regardless.
        """
        # 1. Bootstrap
        bootstrap = BootstrapManager(self._settings)
        bootstrap.start()
        logger = get_logger("agent.runtime.manager")

        # 2. Database
        logger.info("Initializing database")
        self._db = DatabaseManager(self._settings.storage.database_url)
        self._db.initialize()
        Base.metadata.create_all(self._db.engine)
        logger.info("Database initialized")

        # 3. Kubernetes
        logger.info("Initializing Kubernetes client")
        self._k8s_client = KubernetesClient()
        if self._k8s_client.available:
            logger.info("Kubernetes client available")
        else:
            logger.warning(
                "Kubernetes client not available -- running without cluster metadata"
            )

        # 4. Registration
        logger.info("Registering with SentinelAI")
        self._registration_service = RegistrationService(self._db, self._k8s_client)
        response = self._registration_service.register()
        if response:
            logger.info("Registration successful", agent_id=response.agent_id)

            # 5. Credentials
            self._credentials_manager = CredentialsManager(self._db)
            self._credentials_manager.store_credentials(
                agent_id=response.agent_id,
                api_key=response.api_key,
                api_url=response.api_url,
                expires_at=response.expires_at,
            )
            logger.info("Credentials stored")

            # 6. Heartbeat
            self._heartbeat_scheduler = HeartbeatScheduler(response.cluster_id)
            self._heartbeat_scheduler.start()
            logger.info("Heartbeat scheduler started")

            # 7. Detection
            if self._settings.detection.enabled:
                logger.info("Starting detection engine")
                self._detection_service = DetectionService(self._db)
                self._detection_service.start()
                logger.info("Detection engine started")

            # 8. Transport retry loop
            if self._settings.transport.enabled:
                self._start_transport_retry()
        else:
            logger.warning(
                "Registration failed -- continuing without SentinelAI connection"
            )

            # Detection starts regardless of registration status
            if self._settings.detection.enabled:
                logger.info("Starting detection engine")
                self._detection_service = DetectionService(self._db)
                self._detection_service.start()
                logger.info("Detection engine started")

            # Transport retry starts regardless of registration
            if self._settings.transport.enabled:
                self._start_transport_retry()

        self._started = True
        logger.info("Sentinel Agent startup complete")

        # Write health marker for Kubernetes exec probes
        _MARKER_PATH.write_text(datetime.now(UTC).isoformat())

    def _start_transport_retry(self) -> None:
        """Start the transport retry loop in background."""
        from agent.transport.service import TransportService
        from agent.transport.retry import RetryService
        ts = TransportService(self._db)
        interval = getattr(self._settings.transport, 'retry_interval_seconds', 30)
        self._retry_service = RetryService(ts, interval_seconds=interval)
        self._retry_service.start()
        get_logger("agent.runtime.manager").info(
            "transport_retry_started", interval=interval
        )

    def _signal_handler(self, _signum: int, _frame: FrameType | None) -> None:
        """Handle termination signals by triggering shutdown."""
        self._shutdown_event.set()

    def wait(self) -> None:
        """Block the main thread until a termination signal is received.

        Registers handlers for ``SIGTERM`` and ``SIGINT``. Once a signal
        arrives the method returns and the caller should invoke ``stop()``
        to perform a graceful shutdown.
        """
        logger = get_logger("agent.runtime.manager")
        logger.info("Runtime ready -- waiting for shutdown signal")
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        self._shutdown_event.wait()
        logger.info("Shutdown signal received")

    def stop(self) -> None:
        """Perform a graceful shutdown of runtime components.

        Stops the heartbeat scheduler if it was started. Idempotent --
        safe to call multiple times.
        """
        logger = get_logger("agent.runtime.manager")
        if not self._started:
            logger.info("Shutdown skipped -- runtime was not started")
            return
        logger.info("Shutting down Sentinel Agent")
        if self._heartbeat_scheduler and self._heartbeat_scheduler.running:
            self._heartbeat_scheduler.stop()
            logger.info("Heartbeat scheduler stopped")
        if self._detection_service and self._detection_service.started:
            self._detection_service.stop()
            logger.info("Detection engine stopped")
        if self._retry_service and self._retry_service.running:
            self._retry_service.stop()
            logger.info("Transport retry stopped")
        self._started = False
        logger.info("Sentinel Agent shutdown complete")

    @property
    def started(self) -> bool:
        """Whether the startup sequence has completed."""
        return self._started

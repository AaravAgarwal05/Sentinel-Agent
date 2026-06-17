"""Runtime lifecycle manager for the Sentinel Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent.auth.manager import CredentialsManager
from agent.common.kubernetes import KubernetesClient
from agent.common.logging import get_logger
from agent.config.settings import Settings, get_settings
from agent.heartbeat.scheduler import HeartbeatScheduler
from agent.registration.service import RegistrationService
from agent.runtime.bootstrap import BootstrapManager
from agent.storage.database import DatabaseManager

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
        self._started: bool = False

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
        else:
            logger.warning(
                "Registration failed -- continuing without SentinelAI connection"
            )

        self._started = True
        logger.info("Sentinel Agent startup complete")

        # Write health marker for Kubernetes exec probes
        _MARKER_PATH.write_text(datetime.now(UTC).isoformat())

    @property
    def started(self) -> bool:
        """Whether the startup sequence has completed."""
        return self._started

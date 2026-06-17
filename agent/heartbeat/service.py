"""Heartbeat service that sends periodic health updates."""

from __future__ import annotations

from agent.common.logging import get_logger
from agent.config.settings import get_settings
from agent.heartbeat.client import HeartbeatClient
from agent.heartbeat.models import HeartbeatPayload

logger = get_logger(__name__)


class HeartbeatService:
    """Builds heartbeat payloads and dispatches them via the HTTP client.

    Args:
        cluster_id: The cluster identity to include in each heartbeat.
        client: An optional pre-configured
            :class:`HeartbeatClient`. If omitted a new one is created.
    """

    def __init__(
        self,
        cluster_id: str,
        client: HeartbeatClient | None = None,
    ) -> None:
        self._cluster_id: str = cluster_id
        self._client: HeartbeatClient = client or HeartbeatClient()

    def send_heartbeat(self) -> bool:
        """Build and send a heartbeat payload using current agent version and status.

        Returns:
            *True* if the heartbeat was accepted by the control plane (or
            if running in mock mode), *False* otherwise.
        """
        settings = get_settings()
        payload = HeartbeatPayload(
            cluster_id=self._cluster_id,
            agent_version=settings.agent.version,
            status="ok",
        )
        return self._client.send(payload)

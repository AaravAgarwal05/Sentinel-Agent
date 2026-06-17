"""HTTP client for sending heartbeats to SentinelAI."""

from __future__ import annotations

import httpx

from agent.common.logging import get_logger
from agent.config.settings import get_settings
from agent.heartbeat.models import HeartbeatPayload

logger = get_logger(__name__)


class HeartbeatClient:
    """Sends heartbeat payloads to the Sentinel control plane over HTTP.

    Respects ``settings.sentinel.mock_mode``: when *True* the client logs
    the payload and returns *True* without making an HTTP call. When
    *False* it posts to ``{api_url}/agent/heartbeat`` with a Bearer token
    from the registration token setting.
    """

    def __init__(self) -> None:
        """Initialise the client with settings.

        The API URL and registration token are read from the process-wide
        settings on each ``send()`` call so that credential rotation is
        picked up without a restart.
        """
        self._settings = get_settings()

    def send(self, payload: HeartbeatPayload) -> bool:
        """POST ``/agent/heartbeat`` with the given payload.

        Args:
            payload: The heartbeat data to transmit.

        Returns:
            *True* on success (2xx response), *False* on HTTP or
            connection error. Always *True* in mock mode.
        """
        settings = get_settings()

        if settings.sentinel.mock_mode:
            logger.info(
                "mock_heartbeat_send",
                cluster_id=payload.cluster_id,
                agent_version=payload.agent_version,
                status=payload.status,
            )
            return True

        url = f"{settings.sentinel.api_url.rstrip('/')}/agent/heartbeat"
        headers: dict[str, str] = {}

        if settings.sentinel.registration_token:
            headers["Authorization"] = f"Bearer {settings.sentinel.registration_token}"

        try:
            response = httpx.post(
                url,
                json=payload.model_dump(),
                headers=headers,
                timeout=10.0,
            )
            if response.is_success:
                logger.info(
                    "heartbeat_sent",
                    status_code=response.status_code,
                    cluster_id=payload.cluster_id,
                )
                return True

            logger.warning(
                "heartbeat_failed",
                status_code=response.status_code,
                cluster_id=payload.cluster_id,
            )
            return False

        except httpx.RequestError as exc:
            logger.error(
                "heartbeat_connection_error",
                error=str(exc),
                cluster_id=payload.cluster_id,
            )
            return False

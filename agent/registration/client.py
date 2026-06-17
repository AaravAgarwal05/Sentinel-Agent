"""HTTP client for Sentinel agent registration."""
from __future__ import annotations

import uuid

import httpx

from agent.common.logging import get_logger
from agent.config.settings import get_settings
from agent.registration.models import RegistrationPayload, RegistrationResponse

_logger = get_logger("agent.registration.client")


class RegistrationClient:
    """HTTP client that communicates with the Sentinel control plane for registration.

    In mock mode (``settings.sentinel.mock_mode`` is ``True``) no real HTTP
    call is made -- instead a fake ``RegistrationResponse`` is returned so
    the agent can operate without a live control plane.
    """

    def __init__(self) -> None:
        """Store a reference to the application-wide settings."""
        self._settings = get_settings()

    def register(self, payload: RegistrationPayload) -> RegistrationResponse | None:
        """POST ``/agent/register`` with the given payload.

        Behaviour depends on ``settings.sentinel.mock_mode``:

        * **Mock mode** -- log and return a fake :class:`RegistrationResponse`.
        * **Live mode** -- send an authenticated HTTP POST and parse the
          response as a :class:`RegistrationResponse`.

        Args:
            payload: The cluster metadata and registration token to send.

        Returns:
            A :class:`RegistrationResponse` on success, or ``None`` when
            mock mode is off and the server returns a non-2xx status or
            the response body cannot be parsed.
        """
        if self._settings.sentinel.mock_mode:
            _logger.info("mock_registration", payload=payload.model_dump())
            return RegistrationResponse(
                agent_id=f"mock-agent-{uuid.uuid4().hex[:8]}",
                api_key=f"mock-api-key-{uuid.uuid4().hex}",
                api_url=self._settings.sentinel.api_url,
                cluster_id=payload.cluster_id,
            )

        url = f"{self._settings.sentinel.api_url}/agent/register"
        headers = {
            "Authorization": f"Bearer {self._settings.sentinel.registration_token}",
        }

        _logger.info("registration_sending", url=url)

        try:
            response = httpx.post(
                url,
                json=payload.model_dump(),
                headers=headers,
                timeout=30.0,
            )
        except httpx.RequestError as exc:
            _logger.error("registration_http_error", error=str(exc))
            return None

        if not response.is_success:
            _logger.error(
                "registration_http_status",
                status_code=response.status_code,
                body=response.text,
            )
            return None

        try:
            data = response.json()
            result = RegistrationResponse(**data)
            _logger.info("registration_success", agent_id=result.agent_id)
            return result
        except (ValueError, TypeError) as exc:
            _logger.error("registration_parse_error", error=str(exc))
            return None

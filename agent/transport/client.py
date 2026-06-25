"""HTTP client for delivering reports to SentinelAI."""
from __future__ import annotations

import json
from typing import Any

import httpx

from agent.common.logging import get_logger

_logger = get_logger("agent.transport.client")

SENTINELAI_INCIDENTS_PATH = "/incident"


class SentinelAIClient:
    """HTTP client for the SentinelAI control plane API.

    Handles POST of incident + diagnostic payloads. In mock mode no real
    HTTP request is made — the payload is logged and a successful response
    is synthesised.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: int = 10,
        mock_mode: bool = True,
    ) -> None:
        """Initialise the client.

        Args:
            base_url: Base URL of the SentinelAI API (e.g.
                ``https://api.sentinel.example.com``).
            api_key: API key for authenticating with SentinelAI.
            timeout_seconds: HTTP request timeout in seconds (default 10).
            mock_mode: When ``True``, skip real HTTP calls (default ``True``).
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._mock_mode = mock_mode

    def deliver(
        self,
        incident_data: dict[str, Any],
        diagnostic_report_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Deliver incident data to SentinelAI.

        ``diagnostic_report_data`` is accepted for compatibility but is sent
        as top-level fields mixed into the flat Incident payload.

        Args:
            incident_data: Serialised incident fields (flat dict matching
                sentinel-api's Incident model).
            diagnostic_report_data: Ignored — diagnostic fields are already
                merged into ``incident_data`` by the service layer.

        Returns:
            A dict with keys ``accepted`` (bool) and ``correlation_id`` (str
            or None). On success ``accepted`` is ``True``.

        Raises:
            httpx.RequestError: On network / connection failures.
            httpx.HTTPStatusError: On non-2xx responses.
        """
        payload: dict[str, Any] = incident_data

        if self._mock_mode:
            _logger.info(
                "mock_delivery",
                incident_id=incident_data.get("id"),
                diagnostic_report_id=diagnostic_report_data.get("id"),
            )
            return {
                "accepted": True,
                "incident_id": incident_data.get("id"),
                "correlation_id": None,
            }

        _logger.info(
            "report_delivery_started",
            incident_id=incident_data.get("id"),
            diagnostic_report_id=diagnostic_report_data.get("id"),
        )

        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = f"{self._base_url}{SENTINELAI_INCIDENTS_PATH}"

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url,
                headers=headers,
                content=json.dumps(payload, default=str),
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()

        _logger.info(
            "report_delivered",
            incident_id=incident_data.get("id"),
            diagnostic_report_id=diagnostic_report_data.get("id"),
            correlation_id=result.get("correlation_id"),
        )

        return {
            "accepted": result.get("accepted", False),
            "incident_id": incident_data.get("id"),
            "correlation_id": result.get("correlation_id"),
        }

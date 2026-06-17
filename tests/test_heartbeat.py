"""Tests for the heartbeat module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from agent.config.settings import get_settings
from agent.heartbeat.client import HeartbeatClient
from agent.heartbeat.models import HeartbeatPayload
from agent.heartbeat.scheduler import HeartbeatScheduler
from agent.heartbeat.service import HeartbeatService


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests."""
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_heartbeat_payload_construction() -> None:
    """``HeartbeatPayload`` can be constructed with all fields."""
    payload = HeartbeatPayload(
        cluster_id="cluster-1",
        agent_version="1.0.0",
        status="ok",
    )
    assert payload.cluster_id == "cluster-1"
    assert payload.agent_version == "1.0.0"
    assert payload.status == "ok"


def test_heartbeat_payload_default_status() -> None:
    """``status`` defaults to ``"ok"``."""
    payload = HeartbeatPayload(
        cluster_id="cluster-1",
        agent_version="1.0.0",
    )
    assert payload.status == "ok"


# ---------------------------------------------------------------------------
# HeartbeatClient
# ---------------------------------------------------------------------------


class TestHeartbeatClient:
    def test_send_returns_true_in_mock_mode(self) -> None:
        """``send()`` returns ``True`` when ``mock_mode`` is ``True``."""
        client = HeartbeatClient()
        payload = HeartbeatPayload(
            cluster_id="cluster-1",
            agent_version="1.0.0",
        )
        result = client.send(payload)
        assert result is True

    def test_send_returns_false_on_http_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``send()`` returns ``False`` when the HTTP call returns a
        non-2xx status."""
        monkeypatch.setenv("SENTINEL_SENTINEL_MOCK_MODE", "false")
        get_settings.cache_clear()

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = False
        mock_response.status_code = 500

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client = HeartbeatClient()
            payload = HeartbeatPayload(
                cluster_id="cluster-1",
                agent_version="1.0.0",
            )
            result = client.send(payload)
            assert result is False
            mock_post.assert_called_once()

    def test_send_returns_false_on_request_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``send()`` returns ``False`` when an HTTP request exception
        occurs."""
        monkeypatch.setenv("SENTINEL_SENTINEL_MOCK_MODE", "false")
        get_settings.cache_clear()

        with patch("httpx.post", side_effect=httpx.RequestError("connection failed")):
            client = HeartbeatClient()
            payload = HeartbeatPayload(
                cluster_id="cluster-1",
                agent_version="1.0.0",
            )
            result = client.send(payload)
            assert result is False

    def test_send_returns_true_on_success(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``send()`` returns ``True`` when the HTTP call succeeds."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = True
        mock_response.status_code = 200

        monkeypatch.setenv("SENTINEL_SENTINEL_MOCK_MODE", "false")
        monkeypatch.setenv("SENTINEL_SENTINEL_REGISTRATION_TOKEN", "test-token")
        get_settings.cache_clear()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client = HeartbeatClient()
            payload = HeartbeatPayload(
                cluster_id="cluster-1",
                agent_version="1.0.0",
            )
            result = client.send(payload)
            assert result is True
            mock_post.assert_called_once()
            # Verify the bearer token was included
            _call_kwargs = mock_post.call_args.kwargs
            assert "Authorization" in _call_kwargs["headers"]
            assert _call_kwargs["headers"]["Authorization"] == "Bearer test-token"


# ---------------------------------------------------------------------------
# HeartbeatService
# ---------------------------------------------------------------------------


class TestHeartbeatService:
    def test_send_heartbeat_returns_true(self) -> None:
        """``send_heartbeat()`` returns ``True`` on success (mock mode)."""
        service = HeartbeatService(cluster_id="cluster-1")
        result = service.send_heartbeat()
        assert result is True

    def test_send_heartbeat_builds_correct_payload(self) -> None:
        """``send_heartbeat()`` builds a payload with the correct
        ``cluster_id``, version, and ``status``."""
        mock_client = MagicMock(spec=HeartbeatClient)
        mock_client.send.return_value = True

        settings = get_settings()
        service = HeartbeatService(cluster_id="test-cluster", client=mock_client)
        result = service.send_heartbeat()
        assert result is True

        mock_client.send.assert_called_once()
        payload: HeartbeatPayload = mock_client.send.call_args[0][0]
        assert payload.cluster_id == "test-cluster"
        assert payload.agent_version == settings.agent.version
        assert payload.status == "ok"


# ---------------------------------------------------------------------------
# HeartbeatScheduler
# ---------------------------------------------------------------------------


class TestHeartbeatScheduler:
    def test_start_stop_lifecycle(self) -> None:
        """``start()`` and ``stop()`` can be called without error."""
        scheduler = HeartbeatScheduler(cluster_id="cluster-1")
        scheduler.start()
        assert scheduler.running is True
        scheduler.stop()
        assert scheduler.running is False

    def test_running_property_before_start(self) -> None:
        """``running`` is ``False`` before ``start()`` is called."""
        scheduler = HeartbeatScheduler(cluster_id="cluster-1")
        assert scheduler.running is False

    def test_running_property_after_stop(self) -> None:
        """``running`` is ``False`` after ``stop()`` is called."""
        scheduler = HeartbeatScheduler(cluster_id="cluster-1")
        scheduler.start()
        scheduler.stop()
        assert scheduler.running is False

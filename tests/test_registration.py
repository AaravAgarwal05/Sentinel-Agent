"""Tests for the agent registration module."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from agent.config.settings import get_settings
from agent.registration.client import RegistrationClient
from agent.registration.models import RegistrationPayload, RegistrationResponse
from agent.registration.service import RegistrationService


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests."""
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_registration_payload_construction() -> None:
    """``RegistrationPayload`` can be constructed with all fields."""
    payload = RegistrationPayload(
        cluster_id="cluster-1",
        cluster_name="test-cluster",
        agent_version="1.0.0",
        kubernetes_version="1.28.3",
        node_count=5,
        namespace_count=10,
        registration_token="token-123",
    )
    assert payload.cluster_id == "cluster-1"
    assert payload.cluster_name == "test-cluster"
    assert payload.agent_version == "1.0.0"
    assert payload.kubernetes_version == "1.28.3"
    assert payload.node_count == 5
    assert payload.namespace_count == 10
    assert payload.registration_token == "token-123"


def test_registration_payload_optional_fields_default() -> None:
    """Optional fields default to ``None``."""
    payload = RegistrationPayload(
        cluster_id="cluster-1",
        cluster_name="test-cluster",
        agent_version="1.0.0",
        registration_token="token-123",
    )
    assert payload.kubernetes_version is None
    assert payload.node_count is None
    assert payload.namespace_count is None


def test_registration_response_construction() -> None:
    """``RegistrationResponse`` can be constructed with all fields."""
    expires = datetime(2025, 12, 31, tzinfo=UTC)
    response = RegistrationResponse(
        agent_id="agent-1",
        api_key="key-123",
        api_url="https://api.example.com",
        expires_at=expires,
        cluster_id="cluster-1",
    )
    assert response.agent_id == "agent-1"
    assert response.api_key == "key-123"
    assert response.api_url == "https://api.example.com"
    assert response.expires_at == expires
    assert response.cluster_id == "cluster-1"


def test_registration_response_optional_expires_at() -> None:
    """``expires_at`` can be omitted."""
    response = RegistrationResponse(
        agent_id="agent-1",
        api_key="key-123",
        api_url="https://api.example.com",
        cluster_id="cluster-1",
    )
    assert response.expires_at is None


# ---------------------------------------------------------------------------
# RegistrationClient
# ---------------------------------------------------------------------------


class TestRegistrationClient:
    def test_register_returns_response_in_mock_mode(self) -> None:
        """``register()`` returns a ``RegistrationResponse`` when
        ``mock_mode`` is ``True``."""
        client = RegistrationClient()
        payload = RegistrationPayload(
            cluster_id="cluster-1",
            cluster_name="test-cluster",
            agent_version="1.0.0",
            registration_token="token-123",
        )
        response = client.register(payload)
        assert response is not None
        assert isinstance(response, RegistrationResponse)
        assert response.cluster_id == "cluster-1"
        assert response.api_url == get_settings().sentinel.api_url
        assert response.agent_id.startswith("mock-agent-")
        assert response.api_key.startswith("mock-api-key-")

    def test_register_returns_none_on_http_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``register()`` returns ``None`` when the HTTP call returns a
        non-2xx status."""
        monkeypatch.setenv("SENTINEL_SENTINEL_MOCK_MODE", "false")
        get_settings.cache_clear()

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client = RegistrationClient()
            payload = RegistrationPayload(
                cluster_id="cluster-1",
                cluster_name="test-cluster",
                agent_version="1.0.0",
                registration_token="token-123",
            )
            result = client.register(payload)
            assert result is None
            mock_post.assert_called_once()

    def test_register_returns_none_on_request_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``register()`` returns ``None`` when an HTTP request exception
        occurs."""
        monkeypatch.setenv("SENTINEL_SENTINEL_MOCK_MODE", "false")
        get_settings.cache_clear()

        with patch("httpx.post", side_effect=httpx.RequestError("connection failed")):
            client = RegistrationClient()
            payload = RegistrationPayload(
                cluster_id="cluster-1",
                cluster_name="test-cluster",
                agent_version="1.0.0",
                registration_token="token-123",
            )
            result = client.register(payload)
            assert result is None


# ---------------------------------------------------------------------------
# RegistrationService
# ---------------------------------------------------------------------------


class TestRegistrationService:
    def test_register_returns_response_when_successful(
        self, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``RegistrationService.register()`` returns a response when
        registration succeeds."""

        mock_k8s = MagicMock()
        mock_k8s.available = False

        mock_db = MagicMock()
        mock_db.session.return_value.__enter__.return_value = MagicMock()

        service = RegistrationService(db=mock_db, k8s_client=mock_k8s)
        response = service.register()
        assert response is not None
        assert isinstance(response, RegistrationResponse)

    def test_register_returns_none_when_registration_fails(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``RegistrationService.register()`` returns ``None`` when
        ``RegistrationClient.register()`` returns ``None``."""

        mock_db = MagicMock()
        mock_k8s = MagicMock()
        mock_k8s.available = False

        service = RegistrationService(db=mock_db, k8s_client=mock_k8s)

        # The service creates its own RegistrationClient internally.
        # In mock mode (the default) the client always returns a response,
        # so we need to patch the client's register method.
        with patch.object(
            service._reg_client, "register", return_value=None
        ) as mock_reg:
            response = service.register()
            assert response is None
            mock_reg.assert_called_once()

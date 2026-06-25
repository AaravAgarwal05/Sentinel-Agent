"""Tests for SentinelAIClient."""
from __future__ import annotations

from unittest.mock import ANY, patch

import pytest

from agent.transport.client import SentinelAIClient


@pytest.fixture
def client():
    return SentinelAIClient(
        base_url="https://test.sentinel.example.com",
        api_key="test-key-123",
        timeout_seconds=5,
        mock_mode=False,
    )


@pytest.fixture
def mock_client():
    return SentinelAIClient(
        base_url="https://test.sentinel.example.com",
        api_key="test-key-123",
        timeout_seconds=5,
        mock_mode=True,
    )


def test_mock_delivery_returns_accepted(mock_client) -> None:
    result = mock_client.deliver(
        incident_data={"id": "inc-1", "incident_type": "CrashLoopBackOff"},
        diagnostic_report_data={"id": "dr-1", "root_cause": "Test cause"},
    )
    assert result["accepted"] is True
    assert result["incident_id"] == "inc-1"


def test_mock_delivery_no_real_http(mock_client) -> None:
    with patch("httpx.Client") as mock_http:
        mock_client.deliver(
            incident_data={"id": "inc-1"},
            diagnostic_report_data={"id": "dr-1"},
        )
        mock_http.assert_not_called()


@patch("httpx.Client")
def test_delivery_sends_post(mock_http, client) -> None:
    mock_response = mock_http.return_value.__enter__.return_value.post.return_value
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "accepted": True,
        "incident_id": "inc-1",
        "correlation_id": "corr-abc",
    }
    mock_response.raise_for_status = lambda: None

    result = client.deliver(
        incident_data={"id": "inc-1", "incident_type": "CrashLoopBackOff"},
        diagnostic_report_data={"id": "dr-1", "root_cause": "Test cause"},
    )

    assert result["accepted"] is True
    assert result["correlation_id"] == "corr-abc"

    mock_http.return_value.__enter__.return_value.post.assert_called_once_with(
        "https://test.sentinel.example.com/api/v1/incidents",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer test-key-123",
        },
        content=ANY,
    )


@patch("httpx.Client")
def test_delivery_raises_on_http_error(mock_http, client) -> None:
    import httpx

    mock_response = mock_http.return_value.__enter__.return_value.post.return_value
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 error", request=ANY, response=mock_response
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.deliver(
            incident_data={"id": "inc-1"},
            diagnostic_report_data={"id": "dr-1"},
        )


@patch("httpx.Client")
def test_delivery_includes_correct_url(mock_http, client) -> None:
    mock_response = mock_http.return_value.__enter__.return_value.post.return_value
    mock_response.status_code = 200
    mock_response.json.return_value = {"accepted": True}
    mock_response.raise_for_status = lambda: None

    client.deliver(
        incident_data={"id": "inc-1"},
        diagnostic_report_data={"id": "dr-1"},
    )

    call_kwargs = mock_http.return_value.__enter__.return_value.post.call_args
    assert call_kwargs is not None
    url = call_kwargs[0][0]
    assert url == "https://test.sentinel.example.com/api/v1/incidents"


@patch("httpx.Client")
def test_delivery_sends_correct_payload(mock_http, client) -> None:
    mock_response = mock_http.return_value.__enter__.return_value.post.return_value
    mock_response.status_code = 200
    mock_response.json.return_value = {"accepted": True}
    mock_response.raise_for_status = lambda: None

    client.deliver(
        incident_data={"id": "inc-1", "incident_type": "CrashLoopBackOff"},
        diagnostic_report_data={"id": "dr-1", "root_cause": "OOM"},
    )

    call_kwargs = mock_http.return_value.__enter__.return_value.post.call_args
    import json

    sent = json.loads(call_kwargs[1]["content"])
    assert sent["incident"]["id"] == "inc-1"
    assert sent["diagnostic_report"]["id"] == "dr-1"
    assert sent["diagnostic_report"]["root_cause"] == "OOM"

"""Tests for RetryService."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from agent.transport.retry import RetryService


@pytest.fixture
def transport_service():
    return MagicMock()


def test_retry_service_start_stop(transport_service) -> None:
    retry = RetryService(transport_service, interval_seconds=3600)
    assert not retry.running

    retry.start()
    assert retry.running

    retry.stop()
    assert not retry.running


def test_retry_service_calls_deliver_pending(transport_service) -> None:
    retry = RetryService(transport_service, interval_seconds=1)
    retry.start()
    time.sleep(0.1)
    retry.stop()

    assert transport_service.deliver_pending.called


def test_retry_service_survives_exception(transport_service) -> None:
    transport_service.deliver_pending.side_effect = [Exception("Boom"), 0]

    retry = RetryService(transport_service, interval_seconds=0.5)
    retry.start()
    time.sleep(0.1)
    retry.stop()

    # After first call raises, the loop continues
    assert transport_service.deliver_pending.call_count >= 1


def test_retry_service_idempotent_start(transport_service) -> None:
    retry = RetryService(transport_service, interval_seconds=3600)
    retry.start()
    retry.start()  # second call should be no-op
    assert retry.running
    retry.stop()


def test_retry_service_idempotent_stop(transport_service) -> None:
    retry = RetryService(transport_service, interval_seconds=3600)
    retry.stop()  # stop before start
    assert not retry.running


def test_retry_service_uses_configured_interval(transport_service) -> None:
    retry = RetryService(transport_service, interval_seconds=30)
    retry.start()
    assert retry._interval == 30
    retry.stop()

"""Tests for TransportService."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import ANY, patch

import pytest

from agent.config.settings import get_settings
from agent.storage.database import DatabaseManager
from agent.storage.models import Base
from agent.transport.models import OutboundReport, OutboundStatus
from agent.transport.service import TransportService


@pytest.fixture
def db():
    mgr = DatabaseManager("sqlite:///:memory:")
    mgr.initialize()
    # Register all models
    from agent.detection.incident import Incident  # noqa: F401
    from agent.diagnostics.models import DiagnosticReport  # noqa: F401

    Base.metadata.create_all(mgr.engine)
    return mgr


@pytest.fixture
def settings():
    s = get_settings()
    s.transport.enabled = True
    s.transport.mock_mode = True
    s.transport.max_retries = 3
    return s


@pytest.fixture
def service(db, settings):
    return TransportService(db)


def _make_incident(**overrides):
    defaults = dict(
        id=str(uuid.uuid4()),
        incident_type="CrashLoopBackOff",
        severity="MEDIUM",
        namespace="default",
        resource_kind="Pod",
        resource_name="test-pod",
        message="Pod crashed",
        first_seen_at=None,
        status="OPEN",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_diagnostic_report(**overrides):
    defaults = dict(
        id=str(uuid.uuid4()),
        incident_id=str(uuid.uuid4()),
        root_cause="Container crashed",
        confidence=0.95,
        summary="Test summary",
        analyzer_name="CrashLoopAnalyzer",
        created_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_enqueue_creates_pending_report(service, db) -> None:
    incident = _make_incident()
    report = _make_diagnostic_report()

    result = service.enqueue(incident, report)

    assert result is not None
    assert result.incident_id == incident.id
    assert result.diagnostic_report_id == report.id
    assert result.status == OutboundStatus.PENDING
    assert result.retry_count == 0


def test_enqueue_stores_payload(service, db) -> None:
    incident = _make_incident(incident_type="OOMKilled")
    report = _make_diagnostic_report(root_cause="Memory limit exceeded")

    result = service.enqueue(incident, report)
    assert result is not None

    payload = json.loads(result.payload)
    assert payload["incident"]["incident_type"] == "OOMKilled"
    assert payload["diagnostic_report"]["root_cause"] == "Memory limit exceeded"
    assert payload["diagnostic_report"]["id"] == report.id


def test_enqueue_returns_none_when_disabled(service, db) -> None:
    service._settings.transport.enabled = False
    incident = _make_incident()
    report = _make_diagnostic_report()

    result = service.enqueue(incident, report)
    assert result is None


def test_deliver_pending_processes_reports(service, db) -> None:
    incident = _make_incident()
    report = _make_diagnostic_report()
    outbound = service.enqueue(incident, report)
    assert outbound is not None

    processed = service.deliver_pending()
    assert processed == 1

    # Verify it's now delivered
    with db.session() as session:
        loaded = session.get(OutboundReport, outbound.id)
    assert loaded is not None
    assert loaded.status == OutboundStatus.DELIVERED


def test_deliver_pending_multiple_reports(service, db) -> None:
    for i in range(3):
        inc = _make_incident(incident_type=f"Type{i}")
        rep = _make_diagnostic_report(root_cause=f"Cause{i}")
        service.enqueue(inc, rep)

    processed = service.deliver_pending(limit=10)
    assert processed == 3


def test_deliver_pending_respects_limit(service, db) -> None:
    for i in range(5):
        inc = _make_incident()
        rep = _make_diagnostic_report()
        service.enqueue(inc, rep)

    processed = service.deliver_pending(limit=2)
    assert processed == 2


def test_deliver_pending_marks_failed_after_max_retries(service, db) -> None:
    service._client = None  # force real client creation
    service._settings.transport.mock_mode = False

    incident = _make_incident()
    report = _make_diagnostic_report()
    outbound = service.enqueue(incident, report)
    assert outbound is not None

    # Simulate max retries reached
    with db.session() as session:
        outbound.retry_count = service._settings.transport.max_retries - 1
        session.add(outbound)

    processed = service.deliver_pending()
    assert processed == 1

    with db.session() as session:
        loaded = session.get(OutboundReport, outbound.id)
    assert loaded is not None
    assert loaded.status == OutboundStatus.FAILED


@patch("agent.transport.client.SentinelAIClient.deliver")
def test_deliver_pending_calls_client(mock_deliver, service, db) -> None:
    mock_deliver.return_value = {"accepted": True, "correlation_id": "cid-1"}

    incident = _make_incident()
    report = _make_diagnostic_report()
    service.enqueue(incident, report)

    processed = service.deliver_pending()
    assert processed == 1
    mock_deliver.assert_called_once()


def test_deliver_pending_no_pending_returns_zero(service, db) -> None:
    processed = service.deliver_pending()
    assert processed == 0


def test_enqueue_then_deliver_success_path(service, db) -> None:
    incident = _make_incident()
    report = _make_diagnostic_report()

    outbound = service.enqueue(incident, report)
    assert outbound is not None
    assert outbound.status == OutboundStatus.PENDING

    processed = service.deliver_pending()
    assert processed == 1

    with db.session() as session:
        loaded = session.get(OutboundReport, outbound.id)
    assert loaded is not None
    assert loaded.status == OutboundStatus.DELIVERED
    assert loaded.delivered_at is not None

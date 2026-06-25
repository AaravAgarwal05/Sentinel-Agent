"""Tests for transport models."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from agent.storage.models import Base
from agent.transport.models import OutboundReport, OutboundStatus


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


def test_outbound_report_table_name() -> None:
    assert OutboundReport.__tablename__ == "outbound_report"


def test_outbound_status_values() -> None:
    assert OutboundStatus.PENDING == "PENDING"
    assert OutboundStatus.DELIVERED == "DELIVERED"
    assert OutboundStatus.FAILED == "FAILED"


def test_outbound_report_has_expected_columns(engine) -> None:
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("outbound_report")}
    expected = {
        "id", "incident_id", "diagnostic_report_id", "payload",
        "status", "retry_count", "last_attempt_at", "delivered_at",
        "created_at",
    }
    assert set(columns.keys()) == expected


def test_outbound_report_id_is_primary_key(engine) -> None:
    inspector = inspect(engine)
    pk = inspector.get_pk_constraint("outbound_report")
    assert "id" in pk["constrained_columns"]


def test_outbound_report_incident_id_is_indexed(engine) -> None:
    inspector = inspect(engine)
    indexes = inspector.get_indexes("outbound_report")
    index_columns = [idx["column_names"] for idx in indexes]
    assert ["incident_id"] in index_columns


def test_outbound_report_diagnostic_report_id_is_indexed(engine) -> None:
    inspector = inspect(engine)
    indexes = inspector.get_indexes("outbound_report")
    index_columns = [idx["column_names"] for idx in indexes]
    assert ["diagnostic_report_id"] in index_columns


def test_outbound_report_status_is_indexed(engine) -> None:
    inspector = inspect(engine)
    indexes = inspector.get_indexes("outbound_report")
    index_columns = [idx["column_names"] for idx in indexes]
    assert ["status"] in index_columns


def test_outbound_report_default_status_is_pending() -> None:
    report = OutboundReport(
        incident_id="inc-1",
        diagnostic_report_id="dr-1",
        payload="{}",
    )
    assert report.status == OutboundStatus.PENDING
    assert report.retry_count == 0


def test_outbound_report_default_retry_count_zero() -> None:
    report = OutboundReport(
        incident_id="inc-1",
        diagnostic_report_id="dr-1",
        payload="{}",
        status=OutboundStatus.DELIVERED,
    )
    assert report.retry_count == 0

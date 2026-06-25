"""Tests for the DiagnosticReport model."""
from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, inspect

from agent.diagnostics.models import DiagnosticReport
from agent.storage.models import Base


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


def test_diagnostic_report_table_name() -> None:
    assert DiagnosticReport.__tablename__ == "diagnostic_report"


def test_diagnostic_report_has_expected_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("diagnostic_report")}
    assert "id" in columns
    assert "incident_id" in columns
    assert "root_cause" in columns
    assert "confidence" in columns
    assert "summary" in columns
    assert "evidence" in columns
    assert "analyzer_name" in columns
    assert "created_at" in columns


def test_diagnostic_report_id_is_primary_key(engine: Engine) -> None:
    inspector = inspect(engine)
    pk = inspector.get_pk_constraint("diagnostic_report")
    assert "id" in pk["constrained_columns"]


def test_diagnostic_report_incident_id_is_indexed(engine: Engine) -> None:
    inspector = inspect(engine)
    indexes = inspector.get_indexes("diagnostic_report")
    index_columns = [idx["column_names"] for idx in indexes]
    assert ["incident_id"] in index_columns


def test_diagnostic_report_root_cause_not_nullable(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("diagnostic_report")}
    assert not columns["root_cause"]["nullable"]


def test_diagnostic_report_confidence_is_float(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("diagnostic_report")}
    assert columns["confidence"]["type"].python_type is float


def test_diagnostic_report_summary_nullable(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("diagnostic_report")}
    assert columns["summary"]["nullable"] is True


def test_diagnostic_report_evidence_nullable(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("diagnostic_report")}
    assert columns["evidence"]["nullable"] is True

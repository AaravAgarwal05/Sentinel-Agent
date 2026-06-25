"""Tests for DiagnosticReportRepository."""
from __future__ import annotations

import uuid

import pytest

from agent.diagnostics.models import DiagnosticReport
from agent.diagnostics.repositories import DiagnosticReportRepository
from agent.storage.database import DatabaseManager
from agent.storage.models import Base


@pytest.fixture
def db() -> DatabaseManager:
    mgr = DatabaseManager("sqlite:///:memory:")
    mgr.initialize()
    Base.metadata.create_all(mgr.engine)
    return mgr


@pytest.fixture
def repo(db: DatabaseManager) -> DiagnosticReportRepository:
    return DiagnosticReportRepository(db)


def _create_report(
    db: DatabaseManager,
    incident_id: str,
    root_cause: str = "Test cause",
    confidence: float = 0.95,
    analyzer_name: str = "TestAnalyzer",
) -> DiagnosticReport:
    report = DiagnosticReport(
        id=str(uuid.uuid4()),
        incident_id=incident_id,
        root_cause=root_cause,
        confidence=confidence,
        analyzer_name=analyzer_name,
    )
    with db.session() as session:
        DiagnosticReportRepository(db).create(session, report)
    return report


def test_create_persists_report(db: DatabaseManager, repo: DiagnosticReportRepository) -> None:
    report_id = str(uuid.uuid4())
    incident_id = str(uuid.uuid4())
    report = DiagnosticReport(
        id=report_id,
        incident_id=incident_id,
        root_cause="Container image does not exist",
        confidence=0.97,
        summary="Test summary",
        evidence={"key": "value"},
        analyzer_name="ImagePullAnalyzer",
    )
    with db.session() as session:
        persisted = repo.create(session, report)
        assert persisted.id == report_id
        assert persisted.root_cause == "Container image does not exist"
        assert persisted.confidence == 0.97
        assert persisted.analyzer_name == "ImagePullAnalyzer"


def test_get_by_incident_returns_reports(
    db: DatabaseManager, repo: DiagnosticReportRepository
) -> None:
    incident_id = str(uuid.uuid4())
    _create_report(db, incident_id, "Cause A")
    _create_report(db, incident_id, "Cause B")

    with db.session() as session:
        results = repo.get_by_incident(session, incident_id)

    assert len(results) == 2
    root_causes = [r.root_cause for r in results]
    assert "Cause A" in root_causes
    assert "Cause B" in root_causes


def test_get_by_incident_returns_empty_for_unknown(
    db: DatabaseManager, repo: DiagnosticReportRepository
) -> None:
    with db.session() as session:
        results = repo.get_by_incident(session, "nonexistent-id")
    assert len(results) == 0


def test_list_recent_returns_reports(
    db: DatabaseManager, repo: DiagnosticReportRepository
) -> None:
    inc1 = str(uuid.uuid4())
    inc2 = str(uuid.uuid4())
    _create_report(db, inc1, "A")
    _create_report(db, inc2, "B")
    _create_report(db, inc1, "C")

    with db.session() as session:
        results = repo.list_recent(session, limit=10)

    assert len(results) == 3


def test_list_recent_respects_limit(
    db: DatabaseManager, repo: DiagnosticReportRepository
) -> None:
    inc1 = str(uuid.uuid4())
    inc2 = str(uuid.uuid4())
    _create_report(db, inc1, "A")
    _create_report(db, inc2, "B")
    _create_report(db, inc1, "C")

    with db.session() as session:
        results = repo.list_recent(session, limit=2)

    assert len(results) == 2

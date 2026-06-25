"""Tests for OutboundReportRepository."""
from __future__ import annotations

import uuid

import pytest

from agent.storage.database import DatabaseManager
from agent.storage.models import Base
from agent.transport.models import OutboundReport, OutboundStatus
from agent.transport.repositories import OutboundReportRepository


@pytest.fixture
def db():
    mgr = DatabaseManager("sqlite:///:memory:")
    mgr.initialize()
    Base.metadata.create_all(mgr.engine)
    return mgr


@pytest.fixture
def repo(db):
    return OutboundReportRepository(db)


def _create_report(
    db,
    incident_id: str | None = None,
    status: OutboundStatus = OutboundStatus.PENDING,
    retry_count: int = 0,
) -> OutboundReport:
    report = OutboundReport(
        id=str(uuid.uuid4()),
        incident_id=incident_id or str(uuid.uuid4()),
        diagnostic_report_id=str(uuid.uuid4()),
        payload='{"test": true}',
        status=status,
        retry_count=retry_count,
    )
    with db.session() as session:
        OutboundReportRepository(db).create(session, report)
    return report


def test_create_persists_report(db, repo) -> None:
    report_id = str(uuid.uuid4())
    report = OutboundReport(
        id=report_id,
        incident_id=str(uuid.uuid4()),
        diagnostic_report_id=str(uuid.uuid4()),
        payload='{"key": "value"}',
    )
    with db.session() as session:
        persisted = repo.create(session, report)
        assert persisted.id == report_id
        assert persisted.payload == '{"key": "value"}'
        assert persisted.status == OutboundStatus.PENDING
        assert persisted.retry_count == 0


def test_get_pending_returns_pending_only(db, repo) -> None:
    _create_report(db, status=OutboundStatus.PENDING)
    _create_report(db, status=OutboundStatus.DELIVERED)
    _create_report(db, status=OutboundStatus.FAILED)

    with db.session() as session:
        pending = repo.get_pending(session)

    assert len(pending) == 1
    assert pending[0].status == OutboundStatus.PENDING


def test_get_pending_returns_oldest_first(db, repo) -> None:
    r1 = _create_report(db, status=OutboundStatus.PENDING)
    r2 = _create_report(db, status=OutboundStatus.PENDING)

    with db.session() as session:
        pending = repo.get_pending(session)

    assert len(pending) == 2
    assert pending[0].id == r1.id
    assert pending[1].id == r2.id


def test_get_pending_respects_limit(db, repo) -> None:
    for _ in range(5):
        _create_report(db, status=OutboundStatus.PENDING)

    with db.session() as session:
        pending = repo.get_pending(session, limit=3)

    assert len(pending) == 3


def test_get_pending_returns_empty_when_none(db, repo) -> None:
    with db.session() as session:
        pending = repo.get_pending(session)

    assert len(pending) == 0


def test_mark_delivered_updates_status(db, repo) -> None:
    report = _create_report(db)
    with db.session() as session:
        repo.mark_delivered(session, report.id)

    with db.session() as session:
        loaded = session.get(OutboundReport, report.id)
    assert loaded is not None
    assert loaded.status == OutboundStatus.DELIVERED
    assert loaded.delivered_at is not None


def test_increment_retry(db, repo) -> None:
    report = _create_report(db, retry_count=2)
    with db.session() as session:
        repo.increment_retry(session, report.id)

    with db.session() as session:
        loaded = session.get(OutboundReport, report.id)
    assert loaded is not None
    assert loaded.retry_count == 3
    assert loaded.last_attempt_at is not None


def test_mark_failed_updates_status(db, repo) -> None:
    report = _create_report(db)
    with db.session() as session:
        repo.mark_failed(session, report.id)

    with db.session() as session:
        loaded = session.get(OutboundReport, report.id)
    assert loaded is not None
    assert loaded.status == OutboundStatus.FAILED

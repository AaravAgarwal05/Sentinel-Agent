"""Integration tests for DiagnosticService."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from agent.collection.service import IncidentContextPackage
from agent.diagnostics.models import DiagnosticReport
from agent.diagnostics.service import DiagnosticService
from agent.storage.database import DatabaseManager
from agent.storage.models import Base


@pytest.fixture
def db() -> DatabaseManager:
    mgr = DatabaseManager("sqlite:///:memory:")
    mgr.initialize()
    # Create all tables needed
    from agent.collection.models import IncidentContext  # noqa: F401
    from agent.detection.incident import Incident  # noqa: F401

    Base.metadata.create_all(mgr.engine)
    return mgr


def _create_incident(
    db: DatabaseManager, incident_id: str, incident_type: str = "CrashLoopBackOff"
) -> Any:
    """Create a minimal incident record for testing."""
    from agent.detection.incident import Incident as IncidentModel
    from agent.detection.incident import IncidentSeverity

    incident = IncidentModel(
        id=incident_id,
        incident_type=incident_type,
        severity=IncidentSeverity.MEDIUM,
        namespace="default",
        resource_kind="Pod",
        resource_name="test-pod",
        message=f"Pod test-pod: {incident_type}",
    )
    with db.session() as session:
        session.add(incident)
        session.flush()
    return incident


def test_diagnostic_service_analyze_incident(db: DatabaseManager) -> None:
    """Full end-to-end: create incident -> run diagnostics -> verify report."""
    incident_id = str(uuid.uuid4())
    _create_incident(db, incident_id, "CrashLoopBackOff")

    # Build context
    pod: dict[str, Any] = {
        "metadata": {"name": "test-pod", "namespace": "default"},
        "status": {
            "phase": "Running",
            "container_statuses": [
                {
                    "name": "app",
                    "restart_count": 5,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off 5m restarting",
                        }
                    },
                }
            ],
        },
    }
    context = IncidentContextPackage(
        incident=SimpleNamespace(id=incident_id, incident_type="CrashLoopBackOff"),  # type: ignore[arg-type]
        pod=pod,
    )

    service = DiagnosticService(db)
    report = service.analyze_incident(incident_id, context)

    assert report is not None
    assert isinstance(report, DiagnosticReport)
    assert report.incident_id == incident_id
    assert "crash" in report.root_cause.lower()
    assert report.confidence >= 0.85
    assert report.analyzer_name == "CrashLoopAnalyzer"


def test_diagnostic_service_image_pull(db: DatabaseManager) -> None:
    """ImagePullBackOff analysis end-to-end."""
    incident_id = str(uuid.uuid4())
    _create_incident(db, incident_id, "ImagePullBackOff")

    pod: dict[str, Any] = {
        "metadata": {"name": "test-pod", "namespace": "default"},
        "status": {
            "phase": "Pending",
            "container_statuses": [
                {
                    "name": "app",
                    "restart_count": 0,
                    "state": {
                        "waiting": {
                            "reason": "ImagePullBackOff",
                            "message": "manifest for image not found",
                        }
                    },
                }
            ],
        },
    }
    context = IncidentContextPackage(
        incident=SimpleNamespace(id=incident_id, incident_type="ImagePullBackOff"),  # type: ignore[arg-type]
        pod=pod,
    )

    service = DiagnosticService(db)
    report = service.analyze_incident(incident_id, context)

    assert report is not None
    assert report.root_cause == "Container image does not exist"
    assert report.confidence >= 0.95
    assert report.analyzer_name == "ImagePullAnalyzer"


def test_diagnostic_service_oomkilled(db: DatabaseManager) -> None:
    """OOMKilled analysis end-to-end."""
    incident_id = str(uuid.uuid4())
    _create_incident(db, incident_id, "OOMKilled")

    pod: dict[str, Any] = {
        "metadata": {"name": "test-pod", "namespace": "default"},
        "status": {
            "phase": "Running",
            "container_statuses": [
                {
                    "name": "app",
                    "restart_count": 2,
                    "state": {
                        "terminated": {
                            "reason": "OOMKilled",
                            "exit_code": 137,
                        }
                    },
                }
            ],
        },
    }
    context = IncidentContextPackage(
        incident=SimpleNamespace(id=incident_id, incident_type="OOMKilled"),  # type: ignore[arg-type]
        pod=pod,
    )

    service = DiagnosticService(db)
    report = service.analyze_incident(incident_id, context)

    assert report is not None
    assert "memory limit" in report.root_cause.lower()
    assert report.confidence >= 0.95
    assert report.analyzer_name == "OOMKilledAnalyzer"


def test_diagnostic_service_unknown_type(db: DatabaseManager) -> None:
    """Unknown incident type returns None."""
    incident_id = str(uuid.uuid4())
    _create_incident(db, incident_id, "SomeUnknownType")

    service = DiagnosticService(db)
    report = service.analyze_incident(incident_id)

    assert report is None


def test_diagnostic_service_nonexistent_incident(db: DatabaseManager) -> None:
    """Non-existent incident ID returns None."""
    service = DiagnosticService(db)
    report = service.analyze_incident("nonexistent-id")
    assert report is None


def test_diagnostic_report_persisted(db: DatabaseManager) -> None:
    """Verify report is actually stored in the database."""
    incident_id = str(uuid.uuid4())
    _create_incident(db, incident_id, "CrashLoopBackOff")

    pod: dict[str, Any] = {
        "metadata": {"name": "test-pod", "namespace": "default"},
        "status": {
            "phase": "Running",
            "container_statuses": [
                {
                    "name": "app",
                    "restart_count": 5,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "",
                        }
                    },
                }
            ],
        },
    }
    context = IncidentContextPackage(
        incident=SimpleNamespace(id=incident_id, incident_type="CrashLoopBackOff"),  # type: ignore[arg-type]
        pod=pod,
    )

    service = DiagnosticService(db)
    report = service.analyze_incident(incident_id, context)
    assert report is not None

    # Verify it was persisted
    from agent.diagnostics.repositories import DiagnosticReportRepository

    repo = DiagnosticReportRepository(db)
    with db.session() as session:
        loaded = repo.get_by_incident(session, incident_id)
    assert len(loaded) == 1
    assert loaded[0].id == report.id
    assert loaded[0].root_cause == report.root_cause

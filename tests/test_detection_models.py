"""Tests for detection domain models."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from agent.detection.incident import Incident, IncidentSeverity, IncidentStatus
from agent.detection.models import IncidentCandidate, IncidentResponse


class TestIncidentStatus:
    def test_has_open_value(self) -> None:
        assert IncidentStatus.OPEN.value == "OPEN"

    def test_has_resolved_value(self) -> None:
        assert IncidentStatus.RESOLVED.value == "RESOLVED"

    def test_is_string_enum(self) -> None:
        assert isinstance(IncidentStatus.OPEN, str)


class TestIncidentSeverity:
    def test_has_low_value(self) -> None:
        assert IncidentSeverity.LOW.value == "LOW"

    def test_has_medium_value(self) -> None:
        assert IncidentSeverity.MEDIUM.value == "MEDIUM"

    def test_has_high_value(self) -> None:
        assert IncidentSeverity.HIGH.value == "HIGH"

    def test_has_critical_value(self) -> None:
        assert IncidentSeverity.CRITICAL.value == "CRITICAL"

    def test_values_are_strings(self) -> None:
        for severity in IncidentSeverity:
            assert isinstance(severity.value, str)


class TestIncidentModel:
    """Tests for the SQLAlchemy Incident ORM model."""

    def test_has_correct_tablename(self) -> None:
        assert Incident.__tablename__ == "incident"

    def test_default_id_is_uuid_string(self, tmp_path: Path) -> None:
        from agent.storage.database import DatabaseManager
        from agent.storage.models import Base
        db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
        db.initialize()
        Base.metadata.create_all(db.engine)
        incident = Incident(
            incident_type="CrashLoopBackOff",
            severity=IncidentSeverity.CRITICAL,
            namespace="default",
            resource_kind="Pod",
            resource_name="my-pod",
            message="container-1 crashed",
        )
        with db.session() as session:
            session.add(incident)
            session.flush()
            assert incident.id is not None
            assert isinstance(incident.id, str)
            # Confirm it's a valid UUID
            UUID(incident.id)

    def test_default_status_is_open(self, tmp_path: Path) -> None:
        from agent.storage.database import DatabaseManager
        from agent.storage.models import Base
        db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
        db.initialize()
        Base.metadata.create_all(db.engine)
        incident = Incident(
            incident_type="CrashLoopBackOff",
            severity=IncidentSeverity.CRITICAL,
            namespace="default",
            resource_kind="Pod",
            resource_name="my-pod",
            message="container-1 crashed",
        )
        with db.session() as session:
            session.add(incident)
            session.flush()
            assert incident.status == IncidentStatus.OPEN

    def test_explicit_id_is_preserved(self) -> None:
        incident = Incident(
            id="custom-id-123",
            incident_type="OOMKilled",
            severity=IncidentSeverity.HIGH,
            namespace="production",
            resource_kind="Pod",
            resource_name="web-1",
            message="OOM killed",
        )
        assert incident.id == "custom-id-123"

    def test_explicit_status_is_preserved(self) -> None:
        incident = Incident(
            incident_type="ImagePullBackOff",
            severity=IncidentSeverity.MEDIUM,
            namespace="staging",
            resource_kind="Pod",
            resource_name="app-1",
            message="image pull failed",
            status=IncidentStatus.RESOLVED,
        )
        assert incident.status == IncidentStatus.RESOLVED

    def test_all_fields_are_set(self) -> None:
        incident = Incident(
            incident_type="CrashLoopBackOff",
            severity=IncidentSeverity.CRITICAL,
            namespace="default",
            resource_kind="Pod",
            resource_name="my-pod",
            message="Container my-container in CrashLoopBackOff",
            status=IncidentStatus.OPEN,
        )
        assert incident.incident_type == "CrashLoopBackOff"
        assert incident.severity == IncidentSeverity.CRITICAL
        assert incident.namespace == "default"
        assert incident.resource_kind == "Pod"
        assert incident.resource_name == "my-pod"
        assert incident.message == "Container my-container in CrashLoopBackOff"
        assert incident.status == IncidentStatus.OPEN

    def test_timestamps_default_to_none_before_flush(self) -> None:
        incident = Incident(
            incident_type="CrashLoopBackOff",
            severity=IncidentSeverity.CRITICAL,
            namespace="default",
            resource_kind="Pod",
            resource_name="my-pod",
            message="crashed",
        )
        # server_default columns are None until the row is flushed
        assert incident.first_seen_at is None
        assert incident.last_seen_at is None


class TestIncidentCandidate:
    """Tests for the IncidentCandidate Pydantic model."""

    def test_creation_with_all_fields(self) -> None:
        candidate = IncidentCandidate(
            incident_type="CrashLoopBackOff",
            severity=IncidentSeverity.CRITICAL,
            namespace="default",
            resource_kind="Pod",
            resource_name="my-pod",
            message="Container crashed",
        )
        assert candidate.incident_type == "CrashLoopBackOff"
        assert candidate.severity == IncidentSeverity.CRITICAL
        assert candidate.namespace == "default"
        assert candidate.resource_kind == "Pod"
        assert candidate.resource_name == "my-pod"
        assert candidate.message == "Container crashed"

    def test_rejects_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            IncidentCandidate(
                incident_type="CrashLoopBackOff",
                severity=IncidentSeverity.CRITICAL,
                namespace="default",
                resource_kind="Pod",
                # resource_name omitted
                message="crashed",
            )  # type: ignore[call-arg]

    def test_rejects_invalid_severity_type(self) -> None:
        with pytest.raises(ValidationError):
            IncidentCandidate(
                incident_type="CrashLoopBackOff",
                severity="INVALID",  # type: ignore[arg-type]
                namespace="default",
                resource_kind="Pod",
                resource_name="my-pod",
                message="crashed",
            )


class TestIncidentResponse:
    """Tests for the IncidentResponse Pydantic model."""

    def test_creation_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        response = IncidentResponse(
            id="inc-1",
            incident_type="CrashLoopBackOff",
            severity=IncidentSeverity.CRITICAL,
            namespace="default",
            resource_kind="Pod",
            resource_name="my-pod",
            message="crashed",
            first_seen_at=now,
            last_seen_at=now,
            status=IncidentStatus.OPEN,
        )
        assert response.id == "inc-1"
        assert response.first_seen_at == now
        assert response.last_seen_at == now
        assert response.status == IncidentStatus.OPEN

    def test_rejects_invalid_status(self) -> None:
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            IncidentResponse(
                id="inc-1",
                incident_type="CrashLoopBackOff",
                severity=IncidentSeverity.CRITICAL,
                namespace="default",
                resource_kind="Pod",
                resource_name="my-pod",
                message="crashed",
                first_seen_at=now,
                last_seen_at=now,
                status="INVALID",  # type: ignore[arg-type]
            )

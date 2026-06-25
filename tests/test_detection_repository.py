"""Tests for the IncidentRepository."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text

from agent.detection.incident import Incident, IncidentSeverity, IncidentStatus
from agent.detection.repositories import IncidentRepository
from agent.storage.database import DatabaseManager
from agent.storage.models import Base


def _file_url(tmp_path: Path, name: str = "test.db") -> str:
    """Build a ``sqlite:///<abs path>`` URL for a temp file."""
    return f"sqlite:///{tmp_path / name}"


def _init_db(tmp_path: Path) -> DatabaseManager:
    """Create and initialize a DatabaseManager, creating all tables."""
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    Base.metadata.create_all(db.engine)
    return db


def _make_incident(
    incident_type: str = "CrashLoopBackOff",
    severity: IncidentSeverity = IncidentSeverity.CRITICAL,
    namespace: str = "default",
    resource_name: str = "my-pod",
    message: str = "crashed",
    status: IncidentStatus = IncidentStatus.OPEN,
) -> Incident:
    return Incident(
        incident_type=incident_type,
        severity=severity,
        namespace=namespace,
        resource_kind="Pod",
        resource_name=resource_name,
        message=message,
        status=status,
    )


class TestIncidentRepositoryCreate:
    def test_create_inserts_a_row(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)
        incident = _make_incident()

        with db.session() as session:
            created = repo.create(session, incident)
            assert created.id is not None
            assert created.incident_type == "CrashLoopBackOff"

        # Verify persistence via raw SQL
        with db.session() as session:
            row = session.execute(
                text("SELECT incident_type FROM incident WHERE id = :id"),
                {"id": created.id},
            ).scalar()
            assert row == "CrashLoopBackOff"

    def test_create_assigns_uuid_id(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)
        incident = _make_incident()

        with db.session() as session:
            created = repo.create(session, incident)
            # UUID4 strings are 36 chars (32 hex + 4 dashes)
            assert len(created.id) == 36


class TestIncidentRepositoryGetById:
    def test_returns_existing_incident(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)
        incident = _make_incident()

        with db.session() as session:
            created = repo.create(session, incident)
            incident_id = created.id

        with db.session() as session:
            found = repo.get_by_id(session, incident_id)
            assert found is not None
            assert found.id == incident_id
            assert found.incident_type == "CrashLoopBackOff"

    def test_returns_none_for_missing(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            found = repo.get_by_id(session, "nonexistent-id")
            assert found is None


class TestIncidentRepositoryListOpen:
    def test_returns_only_open_incidents(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(session, _make_incident(resource_name="open-pod"))
            repo.create(
                session,
                _make_incident(
                    resource_name="resolved-pod",
                    status=IncidentStatus.RESOLVED,
                ),
            )

        with db.session() as session:
            open_incidents = repo.list_open(session)
            assert len(open_incidents) == 1
            assert open_incidents[0].resource_name == "open-pod"

    def test_returns_empty_when_no_open(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    resource_name="resolved-pod",
                    status=IncidentStatus.RESOLVED,
                ),
            )

        with db.session() as session:
            open_incidents = repo.list_open(session)
            assert len(open_incidents) == 0

    def test_orders_by_first_seen_descending(self, tmp_path: Path) -> None:
        import time
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            first = repo.create(
                session, _make_incident(resource_name="first-pod")
            )
        time.sleep(1.1)
        with db.session() as session:
            second = repo.create(
                session, _make_incident(resource_name="second-pod")
            )

        with db.session() as session:
            results = repo.list_open(session)
            # Most recent (second) should come first
            assert results[0].resource_name == second.resource_name
            assert results[1].resource_name == first.resource_name


class TestIncidentRepositoryFindOpenDuplicate:
    def test_finds_matching_open_incident(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )

        with db.session() as session:
            found = repo.find_open_duplicate(
                session,
                incident_type="CrashLoopBackOff",
                namespace="default",
                resource_name="my-pod",
            )
            assert found is not None
            assert found.status == IncidentStatus.OPEN

    def test_returns_none_for_resolved_match(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                    status=IncidentStatus.RESOLVED,
                ),
            )

        with db.session() as session:
            found = repo.find_open_duplicate(
                session,
                incident_type="CrashLoopBackOff",
                namespace="default",
                resource_name="my-pod",
            )
            assert found is None

    def test_returns_none_for_different_type(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )

        with db.session() as session:
            found = repo.find_open_duplicate(
                session,
                incident_type="OOMKilled",
                namespace="default",
                resource_name="my-pod",
            )
            assert found is None

    def test_returns_none_for_different_namespace(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )

        with db.session() as session:
            found = repo.find_open_duplicate(
                session,
                incident_type="CrashLoopBackOff",
                namespace="production",
                resource_name="my-pod",
            )
            assert found is None

    def test_returns_none_for_different_resource_name(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )

        with db.session() as session:
            found = repo.find_open_duplicate(
                session,
                incident_type="CrashLoopBackOff",
                namespace="default",
                resource_name="other-pod",
            )
            assert found is None


class TestIncidentRepositoryMarkResolved:
    def test_marks_incident_as_resolved(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            created = repo.create(
                session, _make_incident(resource_name="my-pod")
            )
            incident_id = created.id

        with db.session() as session:
            repo.mark_resolved(session, incident_id)

        with db.session() as session:
            incident = repo.get_by_id(session, incident_id)
            assert incident is not None
            assert incident.status == IncidentStatus.RESOLVED

    def test_raises_for_nonexistent_id(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            with pytest.raises(ValueError, match="No incident found"):
                repo.mark_resolved(session, "nonexistent-id")


class TestIncidentRepositoryUpdateLastSeen:
    def test_updates_last_seen_timestamp(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            created = repo.create(
                session, _make_incident(resource_name="my-pod")
            )
            incident_id = created.id

        # Get original last_seen_at (will be None until flushed to DB)
        with db.session() as session:
            incident = repo.get_by_id(session, incident_id)
            assert incident is not None
            original = incident.last_seen_at

        with db.session() as session:
            repo.update_last_seen(session, incident_id)

        with db.session() as session:
            incident = repo.get_by_id(session, incident_id)
            assert incident is not None
            # The timestamp should have been updated
            assert incident.last_seen_at is not None
            if original is not None:
                assert incident.last_seen_at >= original

    def test_does_not_raise_for_nonexistent(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            # update_last_seen does not raise when the id does not exist
            repo.update_last_seen(session, "nonexistent-id")


class TestIncidentRepositoryResolvePodIncidents:
    def test_resolves_all_open_for_namespace_and_name(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )
            repo.create(
                session,
                _make_incident(
                    incident_type="OOMKilled",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )

        with db.session() as session:
            resolved = repo.resolve_pod_incidents(
                session, namespace="default", resource_name="my-pod"
            )
            assert resolved == 2

        with db.session() as session:
            stmt = select(Incident).where(
                Incident.namespace == "default",
                Incident.resource_name == "my-pod",
                Incident.status == IncidentStatus.RESOLVED,
            )
            results = session.scalars(stmt).all()
            assert len(results) == 2

    def test_does_not_resolve_already_resolved(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                    status=IncidentStatus.RESOLVED,
                ),
            )
            repo.create(
                session,
                _make_incident(
                    incident_type="OOMKilled",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )

        with db.session() as session:
            resolved = repo.resolve_pod_incidents(
                session, namespace="default", resource_name="my-pod"
            )
            # Only the OPEN one gets resolved
            assert resolved == 1

    def test_does_not_resolve_different_namespace(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )

        with db.session() as session:
            resolved = repo.resolve_pod_incidents(
                session, namespace="other", resource_name="my-pod"
            )
            assert resolved == 0

    def test_does_not_resolve_different_resource_name(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            repo.create(
                session,
                _make_incident(
                    incident_type="CrashLoopBackOff",
                    namespace="default",
                    resource_name="my-pod",
                ),
            )

        with db.session() as session:
            resolved = repo.resolve_pod_incidents(
                session, namespace="default", resource_name="other-pod"
            )
            assert resolved == 0

    def test_returns_zero_when_no_open_incidents(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = IncidentRepository(db)

        with db.session() as session:
            resolved = repo.resolve_pod_incidents(
                session, namespace="default", resource_name="my-pod"
            )
            assert resolved == 0

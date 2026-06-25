"""Integration tests: collection is triggered on new incident, skipped on duplicate."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.detection.incident import Incident, IncidentSeverity, IncidentStatus
from agent.detection.models import IncidentCandidate
from agent.detection.repositories import IncidentRepository
from agent.detection.service import DetectionService
from agent.storage.database import DatabaseManager
from agent.storage.models import Base

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_url(tmp_path: Path, name: str = "test.db") -> str:
    return f"sqlite:///{tmp_path / name}"


def _init_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    Base.metadata.create_all(db.engine)
    return db


def _candidate(
    incident_type: str = "CrashLoopBackOff",
    namespace: str = "default",
    resource_name: str = "fail-pod",
    severity: IncidentSeverity = IncidentSeverity.CRITICAL,
) -> IncidentCandidate:
    return IncidentCandidate(
        incident_type=incident_type,
        severity=severity,
        namespace=namespace,
        resource_kind="Pod",
        resource_name=resource_name,
        message="container crashed",
    )


def _pod(
    name: str = "fail-pod",
    namespace: str = "default",
    container_statuses: list | None = None,
) -> dict:
    if container_statuses is None:
        container_statuses = [{"name": "c1", "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "back-off"}}, "ready": False, "restart_count": 5}]
    return {
        "metadata": {"name": name, "namespace": namespace},
        "status": {"phase": "Running", "container_statuses": container_statuses},
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    return _init_db(tmp_path)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    from agent.config.settings import get_settings
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Collection on new incident
# ---------------------------------------------------------------------------


class TestCollectionOnNewIncident:
    def test_collection_called_for_new_incident(self, db: DatabaseManager) -> None:
        """When a new incident is created, collect_for_incident is called."""
        mock_collection_service = MagicMock()

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)
            candidate = _candidate()
            pod = _pod()

            service._persist_or_update(candidate, pod)

        # Verify collection was called once
        mock_collection_service.collect_for_incident.assert_called_once()
        # The incident should have the correct attributes
        args, _ = mock_collection_service.collect_for_incident.call_args
        incident_arg, pod_arg = args
        assert isinstance(incident_arg, Incident)
        assert incident_arg.incident_type == "CrashLoopBackOff"
        assert incident_arg.namespace == "default"
        assert incident_arg.resource_name == "fail-pod"
        assert incident_arg.status == IncidentStatus.OPEN
        assert pod_arg == pod  # Pod dict passed through

    def test_collection_receives_pod_data(self, db: DatabaseManager) -> None:
        """The pod dict is passed through to collect_for_incident."""
        mock_collection_service = MagicMock()

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)
            pod = _pod(name="crashing-pod", namespace="prod")
            candidate = _candidate(resource_name="crashing-pod")

            service._persist_or_update(candidate, pod)

        args, _ = mock_collection_service.collect_for_incident.call_args
        _, pod_arg = args
        assert pod_arg["metadata"]["name"] == "crashing-pod"
        assert pod_arg["metadata"]["namespace"] == "prod"

    def test_collection_called_via_watch_event_path(self, db: DatabaseManager) -> None:
        """The full watch event flow (handle_event -> persist_or_update) triggers
        collection for a new incident."""
        mock_collection_service = MagicMock()

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)
            event = {"type": "MODIFIED", "object": _pod(name="event-pod")}
            service._handle_event(event)

        # Should have called collect_for_incident
        assert mock_collection_service.collect_for_incident.call_count == 1
        args, _ = mock_collection_service.collect_for_incident.call_args
        incident_arg, _ = args
        assert incident_arg.resource_name == "event-pod"


# ---------------------------------------------------------------------------
# No collection on duplicate (dedup)
# ---------------------------------------------------------------------------


class TestNoCollectionOnDuplicate:
    def test_collection_not_called_on_duplicate(self, db: DatabaseManager) -> None:
        """When the same incident already exists, collection is NOT called again."""
        mock_collection_service = MagicMock()

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)
            candidate = _candidate()
            pod = _pod()

            # First call: new incident -> collection
            service._persist_or_update(candidate, pod)
            assert mock_collection_service.collect_for_incident.call_count == 1

            # Second call: duplicate -> no collection
            service._persist_or_update(candidate, pod)
            assert mock_collection_service.collect_for_incident.call_count == 1

    def test_collection_called_for_different_type_same_pod(self, db: DatabaseManager) -> None:
        """Different incident types for the same pod each trigger collection."""
        mock_collection_service = MagicMock()

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)

            # CrashLoopBackOff
            clb_candidate = _candidate(incident_type="CrashLoopBackOff", resource_name="multi-pod")
            service._persist_or_update(clb_candidate, _pod(name="multi-pod"))
            assert mock_collection_service.collect_for_incident.call_count == 1

            # OOMKilled (different type, same pod)
            oom_candidate = _candidate(incident_type="OOMKilled", resource_name="multi-pod")
            service._persist_or_update(oom_candidate, _pod(name="multi-pod"))
            assert mock_collection_service.collect_for_incident.call_count == 2

    def test_collection_called_for_same_type_different_namespace(self, db: DatabaseManager) -> None:
        """Same incident type in different namespaces each trigger collection."""
        mock_collection_service = MagicMock()

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)

            candidate_ns1 = _candidate(namespace="ns1")
            candidate_ns2 = _candidate(namespace="ns2")

            service._persist_or_update(candidate_ns1, _pod(namespace="ns1"))
            assert mock_collection_service.collect_for_incident.call_count == 1

            service._persist_or_update(candidate_ns2, _pod(namespace="ns2"))
            assert mock_collection_service.collect_for_incident.call_count == 2


# ---------------------------------------------------------------------------
# Collection disabled
# ---------------------------------------------------------------------------


class TestCollectionDisabled:
    def test_no_collection_when_disabled(self, db: DatabaseManager) -> None:
        """When collection.enabled is False, _collection_service is None and
        no collection occurs."""
        with patch("agent.detection.service.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.detection.enabled = True
            mock_settings.collection.enabled = False
            mock_get_settings.return_value = mock_settings

            service = DetectionService(db)
            assert service._collection_service is None

            candidate = _candidate()
            service._persist_or_update(candidate, _pod())

            # No collection service to call; no exception should be raised
            # We verify the incident was still persisted
            with db.session() as session:
                repo = IncidentRepository(db)
                incidents = repo.list_open(session)
            assert len(incidents) == 1

    def test_service_is_none_when_disabled(self, db: DatabaseManager) -> None:
        """DetectionService._collection_service is None when collection disabled."""
        with patch("agent.detection.service.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.detection.enabled = True
            mock_settings.collection.enabled = False
            mock_get_settings.return_value = mock_settings

            service = DetectionService(db)
            assert service._collection_service is None


# ---------------------------------------------------------------------------
# Collection with poll_candidates path (no pod)
# ---------------------------------------------------------------------------


class TestCollectionViaPollerPath:
    def test_collection_called_without_pod_from_poller(self, db: DatabaseManager) -> None:
        """poll_candidates triggers collection without a pod dict."""
        mock_collection_service = MagicMock()

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)
            candidates = [
                {
                    "incident_type": "CrashLoopBackOff",
                    "severity": "CRITICAL",
                    "namespace": "default",
                    "resource_kind": "Pod",
                    "resource_name": "poll-pod",
                    "message": "crashed",
                }
            ]
            service.poll_candidates(candidates)

        # poll_candidates calls _persist_or_update without a pod,
        # so collect_for_incident is called with pod=None
        mock_collection_service.collect_for_incident.assert_called_once()
        args, _ = mock_collection_service.collect_for_incident.call_args
        incident_arg, pod_arg = args
        assert isinstance(incident_arg, Incident)
        assert pod_arg is None  # No pod from poller path


# ---------------------------------------------------------------------------
# Deduplication preserves existing incidents
# ---------------------------------------------------------------------------


class TestDedupWithCollection:
    def test_duplicate_does_not_create_second_incident(self, db: DatabaseManager) -> None:
        """Deduplication in _persist_or_update prevents duplicate incidents."""
        mock_collection_service = MagicMock()

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)
            candidate = _candidate()

            service._persist_or_update(candidate, _pod())
            service._persist_or_update(candidate, _pod())

        # Only one incident in DB
        with db.session() as session:
            repo = IncidentRepository(db)
            incidents = repo.list_open(session)
        assert len(incidents) == 1

    def test_exception_in_collection_does_not_affect_incident(self, db: DatabaseManager) -> None:
        """If collect_for_incident raises, the incident is still persisted."""
        mock_collection_service = MagicMock()
        mock_collection_service.collect_for_incident.side_effect = Exception("Collection failed")

        with patch("agent.collection.service.CollectionService", return_value=mock_collection_service):
            service = DetectionService(db)
            candidate = _candidate()

            # Should not raise even though collection fails
            service._persist_or_update(candidate, _pod())

        # Incident should still be in DB
        with db.session() as session:
            repo = IncidentRepository(db)
            incidents = repo.list_open(session)
        assert len(incidents) == 1
        assert incidents[0].resource_name == "fail-pod"

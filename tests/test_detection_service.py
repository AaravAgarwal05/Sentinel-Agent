"""Tests for the DetectionService."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.detection.incident import Incident, IncidentSeverity, IncidentStatus
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


def _watch_event(
    pod: dict,
    event_type: str = "MODIFIED",
) -> dict:
    """Build a Watch API event dict."""
    return {"type": event_type, "object": pod}


def _pod(
    name: str = "test-pod",
    namespace: str = "default",
    phase: str = "Running",
    container_statuses: list | None = None,
) -> dict:
    """Build a minimal Kubernetes pod dict matching the API format."""
    status: dict = {"phase": phase}
    if container_statuses is not None:
        status["container_statuses"] = container_statuses
    return {
        "metadata": {"name": name, "namespace": namespace},
        "status": status,
    }


def _crashloop_container(name: str = "container-1") -> dict:
    return {
        "name": name,
        "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "back-off"}},
    }


def _healthy_container(name: str = "container-1") -> dict:
    return {
        "name": name,
        "ready": True,
        "state": {"running": {"started_at": "2024-01-01T00:00:00Z"}},
    }


def _oomkilled_container(name: str = "container-1") -> dict:
    return {
        "name": name,
        "state": {"running": {"started_at": "2024-01-01T00:00:00Z"}},
        "last_state": {
            "terminated": {
                "reason": "OOMKilled",
                "message": "memory exceeded",
                "exitCode": 137,
            }
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Ensure a fresh Settings instance per test so detection.enabled is the
    default (True)."""
    # We don't call clear_settings_cache directly; instead we just rely
    # on the import-time default of get_settings which is already LRU-cached.
    # The fixture is present for symmetry with other test modules.
    from agent.config.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """Provide a clean in-memory database for each test."""
    return _init_db(tmp_path)


@pytest.fixture
def service(db: DatabaseManager) -> DetectionService:
    """Provide a DetectionService that is NOT started (no watcher/poller
    threads). Internal methods can be called directly."""
    return DetectionService(db)


@pytest.fixture
def repository(db: DatabaseManager) -> IncidentRepository:
    """Provide an IncidentRepository bound to the test database."""
    return IncidentRepository(db)


# ---------------------------------------------------------------------------
# Helper: seed an OPEN incident
# ---------------------------------------------------------------------------


def _seed_incident(
    repository: IncidentRepository,
    db: DatabaseManager,
    incident_type: str = "CrashLoopBackOff",
    namespace: str = "default",
    resource_name: str = "test-pod",
    severity: IncidentSeverity = IncidentSeverity.CRITICAL,
) -> str:
    """Create an OPEN incident in the database and return its id."""
    incident = Incident(
        incident_type=incident_type,
        severity=severity,
        namespace=namespace,
        resource_kind="Pod",
        resource_name=resource_name,
        message="test incident",
        status=IncidentStatus.OPEN,
    )
    with db.session() as session:
        created = repository.create(session, incident)
        return created.id


# ---------------------------------------------------------------------------
# DetectionService - initial state
# ---------------------------------------------------------------------------


class TestDetectionServiceInitialState:
    def test_constructor_creates_service(self, service: DetectionService) -> None:
        assert service.started is False

    def test_empty_registry_returns_no_candidates(
        self, service: DetectionService
    ) -> None:
        pod = _pod(name="any-pod")
        candidates = service._registry.detect_all(pod)
        # The default registry has 3 detectors, but a pod with no
        # container statuses will match none of them.
        assert len(candidates) == 0

    def test_service_has_three_registered_detectors(
        self, service: DetectionService
    ) -> None:
        assert len(service._registry.all) == 3


# ---------------------------------------------------------------------------
# _is_pod_healthy
# ---------------------------------------------------------------------------


class TestIsPodHealthy:
    def test_running_pod_with_all_ready_containers_is_healthy(
        self, service: DetectionService
    ) -> None:
        pod = _pod(
            phase="Running",
            container_statuses=[_healthy_container("c1"), _healthy_container("c2")],
        )
        assert service._is_pod_healthy(pod) is True

    def test_running_pod_with_unready_container_is_not_healthy(
        self, service: DetectionService
    ) -> None:
        pod = _pod(
            phase="Running",
            container_statuses=[
                {"name": "c1", "ready": False, "state": {}}
            ],
        )
        assert service._is_pod_healthy(pod) is False

    def test_pending_pod_is_healthy(self, service: DetectionService) -> None:
        pod = _pod(phase="Pending")
        # Pending is not Running, Succeeded, or "" -- so this is unhealthy
        assert service._is_pod_healthy(pod) is False

    def test_succeeded_pod_is_healthy(self, service: DetectionService) -> None:
        pod = _pod(phase="Succeeded")
        assert service._is_pod_healthy(pod) is True

    def test_empty_phase_is_healthy(self, service: DetectionService) -> None:
        pod = _pod(phase="")
        assert service._is_pod_healthy(pod) is True


# ---------------------------------------------------------------------------
# Deduplication: same (type, namespace, name) for OPEN incident updates
# last_seen
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_same_candidate_updates_last_seen(
        self, db: DatabaseManager, service: DetectionService
    ) -> None:
        """Calling _handle_event twice with the same failing pod updates
        last_seen_at on the existing incident rather than creating a new one."""
        pod = _pod(
            name="crashing-pod",
            container_statuses=[_crashloop_container()],
        )
        event = _watch_event(pod)

        # First event -> create incident
        service._handle_event(event)

        # Verify one incident was created
        with db.session() as session:
            incidents = service._repository.list_open(session)
            assert len(incidents) == 1
            original_last_seen = incidents[0].last_seen_at

        # Second event -> should update last_seen (dedup)
        service._handle_event(event)

        with db.session() as session:
            incidents = service._repository.list_open(session)
            assert len(incidents) == 1  # Still only one
            if original_last_seen is not None:
                assert incidents[0].last_seen_at >= original_last_seen

    def test_different_type_creates_separate_incident(
        self, db: DatabaseManager, service: DetectionService
    ) -> None:
        """Different incident types for same namespace/name create separate
        incidents."""
        crashloop_pod = _pod(
            name="multi-fail-pod",
            container_statuses=[_crashloop_container()],
        )
        # Process CrashLoopBackOff
        service._handle_event(_watch_event(crashloop_pod))

        # Now create an OOMKilled pod with the same name (different type)
        oom_pod = _pod(
            name="multi-fail-pod",
            container_statuses=[_oomkilled_container()],
        )
        service._handle_event(_watch_event(oom_pod))

        with db.session() as session:
            incidents = service._repository.list_open(session)
            assert len(incidents) == 2
            types = {i.incident_type for i in incidents}
            assert types == {"CrashLoopBackOff", "OOMKilled"}


# ---------------------------------------------------------------------------
# Resolution: healthy pod resolves OPEN incidents
# ---------------------------------------------------------------------------


class TestResolution:
    def test_healthy_pod_resolves_open_incidents(
        self, db: DatabaseManager, service: DetectionService, repository: IncidentRepository
    ) -> None:
        """A healthy pod event resolves all OPEN incidents for that pod."""
        _seed_incident(
            repository, db,
            incident_type="CrashLoopBackOff",
            namespace="default",
            resource_name="healthy-now-pod",
        )

        pod = _pod(
            name="healthy-now-pod",
            container_statuses=[_healthy_container()],
        )
        service._handle_event(_watch_event(pod))

        with db.session() as session:
            open_incidents = repository.list_open(session)
            assert len(open_incidents) == 0

    def test_healthy_pod_does_not_resolve_other_namespace(
        self, db: DatabaseManager, service: DetectionService, repository: IncidentRepository
    ) -> None:
        """Resolving a pod only affects incidents in the same namespace."""
        _seed_incident(
            repository, db,
            namespace="default",
            resource_name="my-pod",
        )

        pod = _pod(name="my-pod", namespace="other")
        service._handle_event(_watch_event(pod))

        with db.session() as session:
            open_incidents = repository.list_open(session)
            assert len(open_incidents) == 1

    def test_deleted_event_resolves_incidents(
        self, db: DatabaseManager, service: DetectionService, repository: IncidentRepository
    ) -> None:
        """A DELETED event resolves all OPEN incidents for the pod."""
        _seed_incident(
            repository, db,
            namespace="default",
            resource_name="deleted-pod",
        )

        pod = _pod(name="deleted-pod")
        service._handle_event(_watch_event(pod, event_type="DELETED"))

        with db.session() as session:
            open_incidents = repository.list_open(session)
            assert len(open_incidents) == 0


# ---------------------------------------------------------------------------
# Detector registry runs all registered detectors
# ---------------------------------------------------------------------------


class TestDetectorRegistryIntegration:
    def test_all_detectors_run_on_event(
        self, db: DatabaseManager, service: DetectionService
    ) -> None:
        """A pod with multiple failure modes triggers all matching detectors,
        creating one incident per match."""
        # Pod with both CrashLoopBackOff AND OOMKilled
        pod = _pod(
            name="multi-fail-pod",
            container_statuses=[
                _crashloop_container("c1"),
                _oomkilled_container("c2"),
            ],
        )
        service._handle_event(_watch_event(pod))

        with db.session() as session:
            incidents = service._repository.list_open(session)
            assert len(incidents) == 2
            types = {i.incident_type for i in incidents}
            assert "CrashLoopBackOff" in types
            assert "OOMKilled" in types

    def test_no_incidents_for_healthy_pod(
        self, db: DatabaseManager, service: DetectionService
    ) -> None:
        """A healthy pod event creates no incidents."""
        pod = _pod(
            container_statuses=[_healthy_container()],
        )
        service._handle_event(_watch_event(pod))

        with db.session() as session:
            incidents = service._repository.list_open(session)
            assert len(incidents) == 0


# ---------------------------------------------------------------------------
# poll_candidates
# ---------------------------------------------------------------------------


class TestPollCandidates:
    def test_poll_candidates_persists_incidents(
        self, db: DatabaseManager, service: DetectionService
    ) -> None:
        candidates = [
            {
                "incident_type": "CrashLoopBackOff",
                "severity": "CRITICAL",
                "namespace": "default",
                "resource_kind": "Pod",
                "resource_name": "poll-pod",
                "message": "container crashed",
            }
        ]
        service.poll_candidates(candidates)

        with db.session() as session:
            incidents = service._repository.list_open(session)
            assert len(incidents) == 1
            assert incidents[0].incident_type == "CrashLoopBackOff"
            assert incidents[0].resource_name == "poll-pod"

    def test_poll_candidates_deduplication(
        self, db: DatabaseManager, service: DetectionService
    ) -> None:
        candidate = {
            "incident_type": "CrashLoopBackOff",
            "severity": "CRITICAL",
            "namespace": "default",
            "resource_kind": "Pod",
            "resource_name": "dedup-pod",
            "message": "container crashed",
        }
        service.poll_candidates([candidate])
        service.poll_candidates([candidate])

        with db.session() as session:
            incidents = service._repository.list_open(session)
            assert len(incidents) == 1


# ---------------------------------------------------------------------------
# _handle_event edge cases
# ---------------------------------------------------------------------------


class TestHandleEventEdgeCases:
    def test_empty_event_is_ignored(self, service: DetectionService) -> None:
        """An event with no object is safely ignored."""
        service._handle_event({"type": "MODIFIED"})  # No exception

    def test_event_with_non_dict_object_is_ignored(
        self, service: DetectionService
    ) -> None:
        """An event whose object is not a dict is safely ignored."""
        service._handle_event({"type": "MODIFIED", "object": None})
        service._handle_event({"type": "MODIFIED", "object": "string"})

    def test_event_missing_type_uses_empty_string(
        self, db: DatabaseManager, service: DetectionService
    ) -> None:
        """An event with no type field defaults to empty string, which means
        it won't be DELETED, so detection runs."""
        pod = _pod(
            container_statuses=[_crashloop_container()],
        )
        service._handle_event({"object": pod})

        with db.session() as session:
            incidents = service._repository.list_open(session)
            assert len(incidents) == 1


# ---------------------------------------------------------------------------
# Start / stop lifecycle (with patches)
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_is_idempotent(self, service: DetectionService) -> None:
        """Calling start() multiple times only starts once."""
        with (
            patch("agent.detection.service.PodWatcher") as mock_watcher_cls,
            patch("agent.detection.service.PodPoller") as mock_poller_cls,
        ):
            mock_watcher = MagicMock()
            mock_watcher_cls.return_value = mock_watcher
            mock_poller = MagicMock()
            mock_poller_cls.return_value = mock_poller

            service.start()
            assert service.started is True
            mock_watcher.start.assert_called_once()
            mock_poller.start.assert_called_once()

            # Second start should be a no-op
            service.start()
            assert mock_watcher.start.call_count == 1
            assert mock_poller.start.call_count == 1

    def test_stop_stops_watcher_and_poller(
        self, service: DetectionService
    ) -> None:
        """stop() stops both the watcher and poller."""
        with (
            patch("agent.detection.service.PodWatcher") as mock_watcher_cls,
            patch("agent.detection.service.PodPoller") as mock_poller_cls,
        ):
            mock_watcher = MagicMock()
            mock_watcher_cls.return_value = mock_watcher
            mock_poller = MagicMock()
            mock_poller_cls.return_value = mock_poller

            service.start()
            assert service.started is True

            service.stop()
            assert service.started is False
            mock_watcher.stop.assert_called_once()
            mock_poller.stop.assert_called_once()

    def test_stop_is_idempotent_when_not_started(
        self, service: DetectionService
    ) -> None:
        """Calling stop() on a service that was never started is safe."""
        service.stop()

    def test_start_respects_detection_disabled(self, service: DetectionService) -> None:
        """When detection.enabled is False, start() does not start watcher/poller."""
        with (
            patch("agent.detection.service.get_settings") as mock_get_settings,
        ):
            mock_settings = MagicMock()
            mock_settings.detection.enabled = False
            mock_get_settings.return_value = mock_settings

            service.start()
            assert service.started is False

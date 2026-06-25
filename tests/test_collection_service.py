"""Tests for the CollectionService orchestrator."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.collection.collectors.base import ContextResult
from agent.collection.collectors.deployment import DeploymentContextCollector
from agent.collection.collectors.events import EventsContextCollector
from agent.collection.collectors.namespace import NamespaceContextCollector
from agent.collection.collectors.node import NodeContextCollector
from agent.collection.collectors.pod import PodContextCollector
from agent.collection.collectors.replicaset import ReplicaSetContextCollector
from agent.collection.models import ContextType
from agent.collection.repositories import IncidentContextRepository
from agent.collection.service import CollectionService, IncidentContextPackage
from agent.detection.incident import Incident, IncidentSeverity, IncidentStatus
from agent.detection.repositories import IncidentRepository
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


def _incident(
    incident_type: str = "CrashLoopBackOff",
    namespace: str = "default",
    resource_name: str = "test-pod",
) -> Incident:
    return Incident(
        incident_type=incident_type,
        severity=IncidentSeverity.CRITICAL,
        namespace=namespace,
        resource_kind="Pod",
        resource_name=resource_name,
        message="test incident",
        status=IncidentStatus.OPEN,
    )


def _pod(
    name: str = "test-pod",
    namespace: str = "default",
) -> dict:
    return {
        "metadata": {"name": name, "namespace": namespace, "uid": "uid-123", "labels": {}, "annotations": {}, "owner_references": []},
        "spec": {"containers": [], "service_account_name": "default", "node_name": "node-1"},
        "status": {"phase": "Running", "conditions": [], "container_statuses": [], "host_ip": "", "pod_ip": "", "qos_class": ""},
    }


_COLLECTOR_SPECS: dict[str, type] = {
    "pod": PodContextCollector,
    "deployment": DeploymentContextCollector,
    "replicaset": ReplicaSetContextCollector,
    "namespace": NamespaceContextCollector,
    "events": EventsContextCollector,
    "node": NodeContextCollector,
}


@contextmanager
def _mock_collectors(service: CollectionService) -> dict[str, MagicMock]:
    """Replace ``service._collectors`` with real collector instances whose
    ``collect`` method is replaced by a ``MagicMock``.

    This ensures that ``type(collector)`` matches the real class and
    ``_COLLECTOR_KEYS`` resolves correctly.
    Each mock's ``collect`` defaults to returning ``None``.
    """
    from unittest.mock import patch as _patch

    import kubernetes.config as k8s_config

    mocks: dict[str, MagicMock] = {}
    real_collectors: list = []

    for key, cls in _COLLECTOR_SPECS.items():
        # Create a real instance, suppressing K8s config loading where needed
        if key in ("namespace", "node"):
            with _patch.object(k8s_config, "load_incluster_config"):
                with _patch.object(k8s_config, "load_kube_config"):
                    inst = cls()
        else:
            inst = cls()

        # Replace collect with a MagicMock
        mock_collect = MagicMock(return_value=None)
        inst.collect = mock_collect  # type: ignore[method-assign]
        mocks[key] = mock_collect
        real_collectors.append(inst)

    original = service._collectors
    service._collectors = real_collectors
    try:
        yield mocks
    finally:
        service._collectors = original


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    return _init_db(tmp_path)


# ---------------------------------------------------------------------------
# Service initialization
# ---------------------------------------------------------------------------


class TestServiceInitialization:
    def test_constructor_creates_service(self, db: DatabaseManager) -> None:
        service = CollectionService(db)
        assert service is not None
        assert service._repository is not None

    def test_collectors_are_initialized_lazily(self, db: DatabaseManager) -> None:
        """Collectors are None until _get_collectors() is called."""
        service = CollectionService(db)
        assert service._collectors is None

        collectors = service._get_collectors()
        assert len(collectors) == 6

    def test_get_collectors_returns_six_collectors(self, db: DatabaseManager) -> None:
        service = CollectionService(db)
        collectors = service._get_collectors()
        assert len(collectors) == 6

    def test_get_collectors_is_cached(self, db: DatabaseManager) -> None:
        service = CollectionService(db)
        collectors1 = service._get_collectors()
        collectors2 = service._get_collectors()
        assert collectors1 is collectors2


# ---------------------------------------------------------------------------
# Collect for incident
# ---------------------------------------------------------------------------


class TestCollectForIncident:
    def test_returns_incident_context_package(self, db: DatabaseManager) -> None:
        """collect_for_incident returns an IncidentContextPackage."""
        incident = _incident()
        pod = _pod()

        inc_repo = IncidentRepository(db)
        with db.session() as session:
            inc_repo.create(session, incident)

        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            mocks["pod"].return_value = ContextResult(context_type="POD", context_payload={"name": "test-pod"})
            mocks["deployment"].return_value = ContextResult(context_type="DEPLOYMENT", context_payload={"name": "test-deploy"})
            mocks["replicaset"].return_value = ContextResult(context_type="REPLICASET", context_payload={"name": "test-rs"})
            mocks["namespace"].return_value = ContextResult(context_type="NAMESPACE", context_payload={"name": "default"})
            mocks["events"].return_value = ContextResult(context_type="EVENTS", context_payload={"events": []})
            mocks["node"].return_value = ContextResult(context_type="NODE", context_payload={"name": "node-1"})

            package = service.collect_for_incident(incident, pod)

        assert isinstance(package, IncidentContextPackage)
        assert package.incident is incident
        assert package.pod == {"name": "test-pod"}
        assert package.deployment == {"name": "test-deploy"}
        assert package.replicaset == {"name": "test-rs"}
        assert package.namespace == {"name": "default"}
        assert package.events == {"events": []}
        assert package.node == {"name": "node-1"}

    def test_persists_context_to_database(self, db: DatabaseManager) -> None:
        """Context records are written to the DB."""
        incident = _incident(incident_type="OOMKilled", resource_name="oom-pod")
        pod = _pod(name="oom-pod")

        inc_repo = IncidentRepository(db)
        with db.session() as session:
            inc_repo.create(session, incident)

        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            mocks["pod"].return_value = ContextResult(context_type="POD", context_payload={"key": "pod"})
            mocks["deployment"].return_value = None
            mocks["replicaset"].return_value = None
            mocks["namespace"].return_value = ContextResult(context_type="NAMESPACE", context_payload={"key": "ns"})
            mocks["events"].return_value = ContextResult(context_type="EVENTS", context_payload={"events": []})
            mocks["node"].return_value = None

            service.collect_for_incident(incident, pod)

        repo = IncidentContextRepository(db)
        with db.session() as session:
            contexts = repo.get_by_incident(session, incident.id)
        assert len(contexts) == 3  # POD, NAMESPACE, EVENTS
        types = {c.context_type for c in contexts}
        assert ContextType.POD in types
        assert ContextType.NAMESPACE in types
        assert ContextType.EVENTS in types

    def test_skips_none_results_from_persist(self, db: DatabaseManager) -> None:
        """Collectors that return None do not create DB records."""
        incident = _incident()
        pod = _pod()

        inc_repo = IncidentRepository(db)
        with db.session() as session:
            inc_repo.create(session, incident)

        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            for mock in mocks.values():
                mock.return_value = None

            service.collect_for_incident(incident, pod)

        repo = IncidentContextRepository(db)
        with db.session() as session:
            contexts = repo.get_by_incident(session, incident.id)
        assert len(contexts) == 0

    def test_returns_empty_package_when_pod_is_none(self, db: DatabaseManager) -> None:
        """When pod is None, collection is skipped and an empty package is returned."""
        incident = _incident()
        service = CollectionService(db)
        package = service.collect_for_incident(incident, pod=None)

        assert isinstance(package, IncidentContextPackage)
        assert package.pod is None
        assert package.deployment is None
        assert package.replicaset is None
        assert package.namespace is None
        assert package.events is None
        assert package.node is None

    def test_continues_on_collector_failure(self, db: DatabaseManager) -> None:
        """When one collector raises an exception, the others still run."""
        incident = _incident()
        pod = _pod()

        inc_repo = IncidentRepository(db)
        with db.session() as session:
            inc_repo.create(session, incident)

        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            mocks["deployment"].side_effect = Exception("Deployment API error")
            mocks["pod"].return_value = ContextResult(context_type="POD", context_payload={"name": "test-pod"})
            mocks["replicaset"].return_value = None
            mocks["namespace"].return_value = None
            mocks["events"].return_value = None
            mocks["node"].return_value = None

            package = service.collect_for_incident(incident, pod)

        assert package.pod == {"name": "test-pod"}
        assert package.deployment is None
        for name, mock in mocks.items():
            mock.assert_called_once()

    def test_continues_when_multiple_collectors_fail(self, db: DatabaseManager) -> None:
        """Multiple collector failures do not stop the remaining collectors."""
        incident = _incident()
        pod = _pod()

        inc_repo = IncidentRepository(db)
        with db.session() as session:
            inc_repo.create(session, incident)

        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            mocks["pod"].side_effect = Exception("Pod error")
            mocks["deployment"].side_effect = Exception("Deploy error")
            mocks["namespace"].return_value = ContextResult(context_type="NAMESPACE", context_payload={"name": "default"})
            mocks["replicaset"].return_value = None
            mocks["events"].return_value = None
            mocks["node"].return_value = None

            package = service.collect_for_incident(incident, pod)

        assert package.pod is None
        assert package.deployment is None
        assert package.namespace == {"name": "default"}

    def test_all_collectors_receive_correct_args(self, db: DatabaseManager) -> None:
        """Each collector is called with (pod, namespace, name)."""
        incident = _incident(namespace="prod", resource_name="web-1")
        pod = _pod(name="web-1", namespace="prod")

        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            for mock in mocks.values():
                mock.return_value = None

            service.collect_for_incident(incident, pod)

        for name, mock in mocks.items():
            mock.assert_called_once_with(pod, "prod", "web-1")


# ---------------------------------------------------------------------------
# _run_collectors
# ---------------------------------------------------------------------------


class TestRunCollectors:
    def test_returns_dict_with_all_keys(self, db: DatabaseManager) -> None:
        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            for mock in mocks.values():
                mock.return_value = None

            results = service._run_collectors(_pod(), "default", "test-pod")

        assert isinstance(results, dict)
        assert set(results.keys()) == {"pod", "deployment", "replicaset", "namespace", "events", "node"}

    def test_returns_none_for_failed_collectors(self, db: DatabaseManager) -> None:
        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            mocks["pod"].side_effect = Exception("API error")
            mocks["deployment"].return_value = ContextResult(context_type="DEPLOYMENT", context_payload={"name": "ok"})
            mocks["replicaset"].return_value = None
            mocks["namespace"].return_value = None
            mocks["events"].return_value = None
            mocks["node"].return_value = None

            results = service._run_collectors(_pod(), "default", "test-pod")

        assert results["pod"] is None
        assert results["deployment"] == {"name": "ok"}

    def test_catches_exceptions_from_all_collectors(self, db: DatabaseManager) -> None:
        """No exception propagates from _run_collectors even if all fail."""
        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            for mock in mocks.values():
                mock.side_effect = Exception("Kaboom")

            # Should not raise
            results = service._run_collectors(_pod(), "default", "test-pod")

        for key, value in results.items():
            assert value is None, f"Collector {key} should have returned None"


# ---------------------------------------------------------------------------
# Context type persistence
# ---------------------------------------------------------------------------


class TestContextTypePreservation:
    def test_correct_context_type_for_each_result(self, db: DatabaseManager) -> None:
        """Each collector's result maps to the correct ContextType in the DB."""
        incident = _incident(resource_name="type-test")
        pod = _pod(name="type-test")

        inc_repo = IncidentRepository(db)
        with db.session() as session:
            inc_repo.create(session, incident)

        service = CollectionService(db)
        with _mock_collectors(service) as mocks:
            mocks["pod"].return_value = ContextResult(context_type="POD", context_payload={"k": "pod"})
            mocks["deployment"].return_value = ContextResult(context_type="DEPLOYMENT", context_payload={"k": "deploy"})
            mocks["replicaset"].return_value = ContextResult(context_type="REPLICASET", context_payload={"k": "rs"})
            mocks["namespace"].return_value = ContextResult(context_type="NAMESPACE", context_payload={"k": "ns"})
            mocks["events"].return_value = ContextResult(context_type="EVENTS", context_payload={"events": [{"k": "evt"}]})
            mocks["node"].return_value = ContextResult(context_type="NODE", context_payload={"k": "node"})

            service.collect_for_incident(incident, pod)

        repo = IncidentContextRepository(db)
        with db.session() as session:
            contexts = repo.get_by_incident(session, incident.id)
        assert len(contexts) == 6
        type_map = {c.context_type: c.context_payload for c in contexts}
        assert type_map[ContextType.POD] == {"k": "pod"}
        assert type_map[ContextType.DEPLOYMENT] == {"k": "deploy"}
        assert type_map[ContextType.REPLICASET] == {"k": "rs"}
        assert type_map[ContextType.NAMESPACE] == {"k": "ns"}
        assert type_map[ContextType.EVENTS] == {"events": [{"k": "evt"}]}
        assert type_map[ContextType.NODE] == {"k": "node"}


# ---------------------------------------------------------------------------
# Package dataclass
# ---------------------------------------------------------------------------


class TestIncidentContextPackage:
    def test_defaults_are_none(self) -> None:
        incident = _incident()
        package = IncidentContextPackage(incident=incident)
        assert package.incident is incident
        assert package.pod is None
        assert package.deployment is None
        assert package.replicaset is None
        assert package.namespace is None
        assert package.events is None
        assert package.node is None

    def test_accepts_explicit_values(self) -> None:
        incident = _incident()
        package = IncidentContextPackage(
            incident=incident,
            pod={"name": "p"},
            deployment={"name": "d"},
            replicaset={"name": "r"},
            namespace={"name": "n"},
            events={"events": []},
            node={"name": "n1"},
        )
        assert package.pod == {"name": "p"}
        assert package.deployment == {"name": "d"}
        assert package.events == {"events": []}

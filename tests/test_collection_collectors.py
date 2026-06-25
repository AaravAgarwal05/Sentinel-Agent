"""Tests for all six context collectors with mocked Kubernetes API."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from kubernetes.client.exceptions import ApiException

from agent.collection.collectors.base import ContextResult
from agent.collection.collectors.deployment import DeploymentContextCollector
from agent.collection.collectors.events import EventsContextCollector
from agent.collection.collectors.namespace import NamespaceContextCollector
from agent.collection.collectors.node import NodeContextCollector
from agent.collection.collectors.pod import PodContextCollector
from agent.collection.collectors.replicaset import ReplicaSetContextCollector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pod(
    name: str = "test-pod",
    namespace: str = "default",
    node_name: str | None = "node-1",
    owner_kind: str | None = None,
    owner_name: str | None = None,
) -> dict:
    """Build a minimal Kubernetes pod dict."""
    metadata: dict = {"name": name, "namespace": namespace, "uid": "uid-123", "labels": {}, "annotations": {}}
    if owner_kind and owner_name:
        metadata["owner_references"] = [{"kind": owner_kind, "name": owner_name, "api_version": "apps/v1", "uid": "owner-uid", "controller": True, "block_owner_deletion": False}]
    else:
        metadata["owner_references"] = []
    spec: dict = {"containers": [], "service_account_name": "default", "node_name": node_name}
    status: dict = {"phase": "Running", "conditions": [], "container_statuses": [], "host_ip": "", "pod_ip": "", "qos_class": ""}
    return {"metadata": metadata, "spec": spec, "status": status}


def _mock_rs_dict(name: str = "test-rs", dep_name: str | None = "test-deploy") -> dict:
    """Build a ReplicaSet dict matching to_dict() output."""
    metadata = {"name": name, "uid": "rs-uid", "creation_timestamp": None, "owner_references": []}
    if dep_name:
        metadata["owner_references"] = [{"kind": "Deployment", "name": dep_name, "api_version": "apps/v1", "uid": "dep-uid", "controller": True, "block_owner_deletion": False}]
    return {
        "metadata": metadata,
        "spec": {"replicas": 3},
        "status": {"available_replicas": 2, "fully_labeled_replicas": 2},
    }


def _mock_deployment_dict(name: str = "test-deploy") -> dict:
    """Build a Deployment dict matching to_dict() output."""
    return {
        "metadata": {"name": name, "uid": "dep-uid", "labels": {"app": "test"}, "creation_timestamp": None},
        "spec": {"replicas": 3, "strategy": {"type": "RollingUpdate", "rolling_update": {"max_surge": "25%", "max_unavailable": "25%"}}},
        "status": {"available_replicas": 2},
    }


def _mock_event(reason: str = "Pulled", message: str = "Successfully pulled image", event_type: str = "Normal", name: str = "test-pod") -> MagicMock:
    """Build a mock Kubernetes event object."""
    event = MagicMock()
    event.reason = reason
    event.message = message
    event.type = event_type
    event.last_timestamp = None
    event.first_timestamp = None
    event.count = 1

    involved = MagicMock()
    involved.name = name
    event.involved_object = involved

    src = MagicMock()
    src.component = "kubelet"
    src.host = "node-1"
    event.source = src

    return event


# ---------------------------------------------------------------------------
# PodContextCollector
# ---------------------------------------------------------------------------


class TestPodContextCollector:
    def test_returns_context_result_with_pod_type(self) -> None:
        collector = PodContextCollector()
        pod = _pod(name="my-pod", namespace="prod")
        result = collector.collect(pod, "prod", "my-pod")
        assert result is not None
        assert result.context_type == "POD"
        assert isinstance(result, ContextResult)

    def test_extracts_metadata(self) -> None:
        collector = PodContextCollector()
        pod = _pod(name="my-pod", namespace="prod")
        result = collector.collect(pod, "prod", "my-pod")
        assert result is not None
        payload = result.context_payload
        assert payload["metadata"]["name"] == "my-pod"
        assert payload["metadata"]["namespace"] == "prod"
        assert payload["metadata"]["uid"] == "uid-123"

    def test_extracts_containers_from_spec(self) -> None:
        collector = PodContextCollector()
        pod = _pod()
        pod["spec"]["containers"] = [
            {"name": "nginx", "image": "nginx:1.25", "resources": {"limits": {"cpu": "100m"}}},
        ]
        result = collector.collect(pod, "default", "test-pod")
        assert result is not None
        containers = result.context_payload["spec"]["containers"]
        assert len(containers) == 1
        assert containers[0]["name"] == "nginx"
        assert containers[0]["image"] == "nginx:1.25"

    def test_extracts_container_statuses(self) -> None:
        collector = PodContextCollector()
        pod = _pod()
        pod["status"]["container_statuses"] = [
            {"name": "c1", "state": {"running": {}}, "ready": True, "restart_count": 0, "image": "nginx", "image_id": "sha256:abc", "container_id": "docker://abc"},
        ]
        result = collector.collect(pod, "default", "test-pod")
        assert result is not None
        statuses = result.context_payload["status"]["container_statuses"]
        assert len(statuses) == 1
        assert statuses[0]["ready"] is True

    def test_extracts_conditions_from_status(self) -> None:
        collector = PodContextCollector()
        pod = _pod()
        pod["status"]["conditions"] = [
            {"type": "Ready", "status": "True", "reason": "PodReady", "message": "", "last_transition_time": None},
        ]
        result = collector.collect(pod, "default", "test-pod")
        assert result is not None
        conditions = result.context_payload["status"]["conditions"]
        assert len(conditions) == 1
        assert conditions[0]["type"] == "Ready"

    def test_extracts_owner_references(self) -> None:
        collector = PodContextCollector()
        pod = _pod(owner_kind="ReplicaSet", owner_name="rs-1")
        result = collector.collect(pod, "default", "test-pod")
        assert result is not None
        refs = result.context_payload["owner_references"]
        assert len(refs) == 1
        assert refs[0]["kind"] == "ReplicaSet"
        assert refs[0]["name"] == "rs-1"

    def test_handles_empty_metadata(self) -> None:
        collector = PodContextCollector()
        pod: dict = {"metadata": {}, "spec": {}, "status": {}}
        result = collector.collect(pod, "default", "")
        assert result is not None
        assert result.context_payload["metadata"]["name"] == ""

    def test_payload_contains_all_sections(self) -> None:
        collector = PodContextCollector()
        pod = _pod()
        result = collector.collect(pod, "default", "test-pod")
        assert result is not None
        assert "metadata" in result.context_payload
        assert "spec" in result.context_payload
        assert "status" in result.context_payload
        assert "owner_references" in result.context_payload


# ---------------------------------------------------------------------------
# DeploymentContextCollector
# ---------------------------------------------------------------------------


class TestDeploymentContextCollector:
    def test_follows_chain_pod_to_deployment(self) -> None:
        """Pod -> ReplicaSet -> Deployment chain resolves correctly."""
        collector = DeploymentContextCollector()
        pod = _pod(owner_kind="ReplicaSet", owner_name="my-rs")

        rs_dict = _mock_rs_dict(name="my-rs", dep_name="my-deploy")
        dep_dict = _mock_deployment_dict(name="my-deploy")

        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps

            mock_rs = MagicMock()
            mock_rs.to_dict.return_value = rs_dict
            mock_apps.read_namespaced_replica_set.return_value = mock_rs

            mock_dep = MagicMock()
            mock_dep.to_dict.return_value = dep_dict
            mock_apps.read_namespaced_deployment.return_value = mock_dep

            result = collector.collect(pod, "default", "test-pod")

        assert result is not None
        assert result.context_type == "DEPLOYMENT"
        assert result.context_payload["name"] == "my-deploy"
        assert result.context_payload["replicas"] == 3
        mock_apps.read_namespaced_replica_set.assert_called_once_with("my-rs", "default")
        mock_apps.read_namespaced_deployment.assert_called_once_with("my-deploy", "default")

    def test_returns_none_when_no_replicaset_owner(self) -> None:
        collector = DeploymentContextCollector()
        pod = _pod()  # No owner references
        with patch("kubernetes.client.AppsV1Api"):
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_returns_none_when_replicaset_not_found(self) -> None:
        collector = DeploymentContextCollector()
        pod = _pod(owner_kind="ReplicaSet", owner_name="missing-rs")

        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_apps.read_namespaced_replica_set.side_effect = ApiException(status=404, reason="Not Found")
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_returns_none_when_replicaset_has_no_deployment_owner(self) -> None:
        collector = DeploymentContextCollector()
        pod = _pod(owner_kind="ReplicaSet", owner_name="orphan-rs")
        rs_dict = _mock_rs_dict(name="orphan-rs", dep_name=None)  # No Deployment owner

        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_rs = MagicMock()
            mock_rs.to_dict.return_value = rs_dict
            mock_apps.read_namespaced_replica_set.return_value = mock_rs
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_returns_none_when_deployment_not_found(self) -> None:
        collector = DeploymentContextCollector()
        pod = _pod(owner_kind="ReplicaSet", owner_name="my-rs")
        rs_dict = _mock_rs_dict(name="my-rs", dep_name="missing-deploy")

        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_rs = MagicMock()
            mock_rs.to_dict.return_value = rs_dict
            mock_apps.read_namespaced_replica_set.return_value = mock_rs
            mock_apps.read_namespaced_deployment.side_effect = ApiException(status=404, reason="Not Found")
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_extracts_strategy_details(self) -> None:
        collector = DeploymentContextCollector()
        pod = _pod(owner_kind="ReplicaSet", owner_name="my-rs")
        rs_dict = _mock_rs_dict(name="my-rs", dep_name="my-deploy")
        dep_dict = _mock_deployment_dict(name="my-deploy")

        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_rs = MagicMock()
            mock_rs.to_dict.return_value = rs_dict
            mock_apps.read_namespaced_replica_set.return_value = mock_rs
            mock_dep = MagicMock()
            mock_dep.to_dict.return_value = dep_dict
            mock_apps.read_namespaced_deployment.return_value = mock_dep
            result = collector.collect(pod, "default", "test-pod")

        assert result is not None
        strategy = result.context_payload["strategy"]
        assert strategy["type"] == "RollingUpdate"
        assert strategy["rolling_update"]["max_surge"] == "25%"


# ---------------------------------------------------------------------------
# EventsContextCollector
# ---------------------------------------------------------------------------


class TestEventsContextCollector:
    def test_returns_events_for_matching_pod(self) -> None:
        with patch("kubernetes.client.CoreV1Api") as mock_core_cls:
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api

            event_list = MagicMock()
            event_list.items = [_mock_event(reason="Pulled", name="test-pod")]
            mock_api.list_namespaced_events.return_value = event_list

            collector = EventsContextCollector()
            pod = _pod(name="test-pod")
            result = collector.collect(pod, "default", "test-pod")

        assert result is not None
        assert result.context_type == "EVENTS"
        assert len(result.context_payload["events"]) == 1
        assert result.context_payload["events"][0]["reason"] == "Pulled"

    def test_returns_all_event_fields(self) -> None:
        with patch("kubernetes.client.CoreV1Api") as mock_core_cls:
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            event_list = MagicMock()
            event_list.items = [_mock_event(reason="BackOff", message="back-off restarting", event_type="Warning", name="test-pod")]
            mock_api.list_namespaced_events.return_value = event_list

            collector = EventsContextCollector()
            result = collector.collect(_pod(name="test-pod"), "default", "test-pod")

        assert result is not None
        event = result.context_payload["events"][0]
        assert event["reason"] == "BackOff"
        assert event["message"] == "back-off restarting"
        assert event["type"] == "Warning"
        assert event["count"] == 1
        assert event["source"]["component"] == "kubelet"

    def test_returns_none_when_no_matching_events(self) -> None:
        with patch("kubernetes.client.CoreV1Api") as mock_core_cls:
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            event_list = MagicMock()
            # Events exist but for a different pod
            event_list.items = [_mock_event(name="other-pod")]
            mock_api.list_namespaced_events.return_value = event_list

            collector = EventsContextCollector()
            result = collector.collect(_pod(name="test-pod"), "default", "test-pod")

        assert result is None

    def test_returns_none_when_api_call_fails(self) -> None:
        with patch("kubernetes.client.CoreV1Api") as mock_core_cls:
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.list_namespaced_events.side_effect = Exception("API error")

            collector = EventsContextCollector()
            result = collector.collect(_pod(name="test-pod"), "default", "test-pod")

        assert result is None

    def test_respects_max_events_limit(self) -> None:
        with patch("kubernetes.client.CoreV1Api") as mock_core_cls:
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            # Create 5 events
            events = [_mock_event(reason=f"Ev{i}", name="test-pod") for i in range(5)]
            event_list = MagicMock()
            event_list.items = events
            mock_api.list_namespaced_events.return_value = event_list

            collector = EventsContextCollector(max_events=3)
            result = collector.collect(_pod(name="test-pod"), "default", "test-pod")

        assert result is not None
        assert len(result.context_payload["events"]) == 3

    def test_filters_events_by_pod_name(self) -> None:
        with patch("kubernetes.client.CoreV1Api") as mock_core_cls:
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            event_list = MagicMock()
            event_list.items = [
                _mock_event(reason="PodEvent", name="test-pod"),
                _mock_event(reason="OtherEvent", name="other-pod"),
            ]
            mock_api.list_namespaced_events.return_value = event_list

            collector = EventsContextCollector()
            result = collector.collect(_pod(name="test-pod"), "default", "test-pod")

        assert result is not None
        reasons = [e["reason"] for e in result.context_payload["events"]]
        assert reasons == ["PodEvent"]
        assert "OtherEvent" not in reasons

    def test_events_list_is_not_none_when_empty(self) -> None:
        """When there are matching events, events key is a list, never None."""
        with patch("kubernetes.client.CoreV1Api") as mock_core_cls:
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            event_list = MagicMock()
            event_list.items = [_mock_event(name="test-pod")]
            mock_api.list_namespaced_events.return_value = event_list

            collector = EventsContextCollector()
            result = collector.collect(_pod(name="test-pod"), "default", "test-pod")

        assert result is not None
        assert isinstance(result.context_payload["events"], list)


# ---------------------------------------------------------------------------
# NamespaceContextCollector
# ---------------------------------------------------------------------------


class _MockNamespace:
    """Minimal mock for a Kubernetes Namespace object returned by read_namespace."""

    def __init__(self, ns_dict: dict) -> None:
        self._dict = ns_dict

    def to_dict(self) -> dict:
        return self._dict


def _mock_namespace_dict(name: str = "default") -> dict:
    return {
        "metadata": {
            "name": name,
            "uid": "ns-uid",
            "labels": {"env": "prod"},
            "annotations": {"owner": "team-a"},
            "creation_timestamp": None,
        },
        "status": {"phase": "Active"},
    }


class TestNamespaceContextCollector:
    def test_returns_namespace_metadata(self) -> None:
        with (
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.config.load_kube_config"),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.read_namespace.return_value = _MockNamespace(_mock_namespace_dict("prod-ns"))

            collector = NamespaceContextCollector()
            result = collector.collect(_pod(namespace="prod-ns"), "prod-ns", "test-pod")

        assert result is not None
        assert result.context_type == "NAMESPACE"
        assert result.context_payload["name"] == "prod-ns"
        assert result.context_payload["labels"]["env"] == "prod"
        assert result.context_payload["status"]["phase"] == "Active"

    def test_returns_fallback_on_api_error(self) -> None:
        with (
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.config.load_kube_config"),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.read_namespace.side_effect = Exception("API error")

            collector = NamespaceContextCollector()
            result = collector.collect(_pod(namespace="broken-ns"), "broken-ns", "test-pod")

        assert result is not None
        assert result.context_type == "NAMESPACE"
        # Should return fallback payload with the namespace name
        assert result.context_payload["name"] == "broken-ns"
        assert result.context_payload["status"]["phase"] == "Unknown"

    def test_fallback_includes_empty_labels_and_annotations(self) -> None:
        with (
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.config.load_kube_config"),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.read_namespace.side_effect = Exception("API error")

            collector = NamespaceContextCollector()
            result = collector.collect(_pod(namespace="err-ns"), "err-ns", "test-pod")

        assert result is not None
        assert result.context_payload["labels"] == {}
        assert result.context_payload["annotations"] == {}

    def test_extracts_creation_timestamp(self) -> None:
        with (
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.config.load_kube_config"),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            from datetime import datetime
            ns_dict = _mock_namespace_dict()
            ns_dict["metadata"]["creation_timestamp"] = datetime(2024, 6, 1, 12, 0, 0)
            mock_api.read_namespace.return_value = _MockNamespace(ns_dict)

            collector = NamespaceContextCollector()
            result = collector.collect(_pod(namespace="default"), "default", "test-pod")

        assert result is not None
        assert "2024-06-01" in result.context_payload["creation_timestamp"]

    def test_has_uid_in_payload(self) -> None:
        with (
            patch("kubernetes.config.load_incluster_config"),
            patch("kubernetes.config.load_kube_config"),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.read_namespace.return_value = _MockNamespace(_mock_namespace_dict())

            collector = NamespaceContextCollector()
            result = collector.collect(_pod(namespace="default"), "default", "test-pod")

        assert result is not None
        assert result.context_payload["uid"] == "ns-uid"


# ---------------------------------------------------------------------------
# NodeContextCollector
# ---------------------------------------------------------------------------


class _MockNode:
    """Minimal mock for a Kubernetes Node object returned by read_node."""

    def __init__(self, node_dict: dict) -> None:
        self._dict = node_dict

    def to_dict(self) -> dict:
        return self._dict


def _mock_node_dict(name: str = "node-1") -> dict:
    return {
        "metadata": {
            "name": name,
            "uid": "node-uid",
            "labels": {"kubernetes.io/role": "worker"},
        },
        "status": {
            "node_info": {
                "kubelet_version": "1.28.0",
                "os_image": "Ubuntu 22.04",
                "architecture": "amd64",
            },
            "conditions": [
                {"type": "Ready", "status": "True", "reason": "KubeletReady", "message": "", "last_heartbeat_time": None, "last_transition_time": None},
            ],
            "allocatable": {"cpu": "4", "memory": "16Gi"},
            "capacity": {"cpu": "4", "memory": "16Gi"},
        },
    }


class TestNodeContextCollector:
    def test_returns_node_details(self) -> None:
        with (
            patch("kubernetes.client.config", MagicMock(), create=True),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.read_node.return_value = _MockNode(_mock_node_dict("worker-1"))

            collector = NodeContextCollector()
            pod = _pod(name="test-pod", node_name="worker-1")
            result = collector.collect(pod, "default", "test-pod")

        assert result is not None
        assert result.context_type == "NODE"
        assert result.context_payload["name"] == "worker-1"
        assert result.context_payload["kubelet_version"] == "1.28.0"
        assert result.context_payload["os_image"] == "Ubuntu 22.04"
        assert result.context_payload["architecture"] == "amd64"

    def test_returns_none_when_pod_not_scheduled(self) -> None:
        with patch("kubernetes.client.config", MagicMock(), create=True):
            collector = NodeContextCollector()
            pod = _pod(name="unscheduled-pod", node_name=None)
            result = collector.collect(pod, "default", "unscheduled-pod")
            assert result is None

    def test_returns_none_when_api_call_fails(self) -> None:
        with (
            patch("kubernetes.client.config", MagicMock(), create=True),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.read_node.side_effect = Exception("API error")

            collector = NodeContextCollector()
            pod = _pod(name="test-pod", node_name="node-fail")
            result = collector.collect(pod, "default", "test-pod")
            assert result is None

    def test_extracts_node_conditions(self) -> None:
        with (
            patch("kubernetes.client.config", MagicMock(), create=True),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.read_node.return_value = _MockNode(_mock_node_dict())

            collector = NodeContextCollector()
            result = collector.collect(_pod(node_name="node-1"), "default", "test-pod")

        assert result is not None
        assert len(result.context_payload["conditions"]) == 1
        assert result.context_payload["conditions"][0]["type"] == "Ready"

    def test_extracts_allocatable_and_capacity(self) -> None:
        with (
            patch("kubernetes.client.config", MagicMock(), create=True),
            patch("kubernetes.client.CoreV1Api") as mock_core_cls,
        ):
            mock_api = MagicMock()
            mock_core_cls.return_value = mock_api
            mock_api.read_node.return_value = _MockNode(_mock_node_dict())

            collector = NodeContextCollector()
            result = collector.collect(_pod(node_name="node-1"), "default", "test-pod")

        assert result is not None
        assert "cpu" in result.context_payload["allocatable"]
        assert "memory" in result.context_payload["capacity"]

    def test_returns_none_when_api_client_not_available(self) -> None:
        """When __init__ could not create the API client, collect returns None."""
        mock_cfg = MagicMock()
        mock_cfg.load_incluster_config.side_effect = Exception("Config error")
        with (
            patch("kubernetes.client.config", mock_cfg, create=True),
            patch("kubernetes.client.CoreV1Api"),
        ):
            collector = NodeContextCollector()
            result = collector.collect(_pod(node_name="node-1"), "default", "test-pod")
            assert result is None


# ---------------------------------------------------------------------------
# ReplicaSetContextCollector
# ---------------------------------------------------------------------------


class _MockReplicaSet:
    """Minimal mock for a Kubernetes ReplicaSet object."""

    def __init__(self, metadata: MagicMock, spec: MagicMock, status: MagicMock) -> None:
        self.metadata = metadata
        self.spec = spec
        self.status = status


def _make_mock_replicaset(
    name: str = "test-rs",
    replicas: int = 3,
    available: int = 2,
    has_owner: bool = True,
) -> _MockReplicaSet:
    metadata = MagicMock()
    metadata.name = name
    metadata.uid = "rs-uid"
    metadata.creation_timestamp = None
    if has_owner:
        owner_ref = MagicMock()
        owner_ref.to_dict.return_value = {"kind": "Deployment", "name": "test-deploy", "api_version": "apps/v1"}
        metadata.owner_references = [owner_ref]
    else:
        metadata.owner_references = None

    spec = MagicMock()
    spec.replicas = replicas

    status = MagicMock()
    status.available_replicas = available
    status.fully_labeled_replicas = available

    return _MockReplicaSet(metadata, spec, status)


class TestReplicaSetContextCollector:
    def test_returns_replicaset_context(self) -> None:
        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_apps.read_namespaced_replica_set.return_value = _make_mock_replicaset("my-rs", replicas=5, available=3)

            collector = ReplicaSetContextCollector()
            pod = _pod(owner_kind="ReplicaSet", owner_name="my-rs")
            result = collector.collect(pod, "default", "test-pod")

        assert result is not None
        assert result.context_type == "REPLICASET"
        assert result.context_payload["name"] == "my-rs"
        assert result.context_payload["replicas"] == 5
        assert result.context_payload["available_replicas"] == 3

    def test_returns_none_when_no_owner_references(self) -> None:
        collector = ReplicaSetContextCollector()
        pod = _pod()  # No owner references
        with patch("kubernetes.client.AppsV1Api"):
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_returns_none_when_owner_is_not_replicaset(self) -> None:
        collector = ReplicaSetContextCollector()
        pod = _pod(owner_kind="Deployment", owner_name="my-deploy")
        with patch("kubernetes.client.AppsV1Api"):
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_returns_none_when_replicaset_not_found(self) -> None:
        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_apps.read_namespaced_replica_set.side_effect = ApiException(status=404, reason="Not Found")

            collector = ReplicaSetContextCollector()
            pod = _pod(owner_kind="ReplicaSet", owner_name="missing-rs")
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_returns_none_on_api_exception(self) -> None:
        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_apps.read_namespaced_replica_set.side_effect = ApiException(status=500, reason="Server Error")

            collector = ReplicaSetContextCollector()
            pod = _pod(owner_kind="ReplicaSet", owner_name="broken-rs")
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_returns_none_on_unexpected_exception(self) -> None:
        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_apps.read_namespaced_replica_set.side_effect = Exception("Unexpected error")

            collector = ReplicaSetContextCollector()
            pod = _pod(owner_kind="ReplicaSet", owner_name="broken-rs")
            result = collector.collect(pod, "default", "test-pod")
        assert result is None

    def test_returns_owner_references_in_payload(self) -> None:
        with patch("kubernetes.client.AppsV1Api") as mock_apps_cls:
            mock_apps = MagicMock()
            mock_apps_cls.return_value = mock_apps
            mock_apps.read_namespaced_replica_set.return_value = _make_mock_replicaset(has_owner=True)

            collector = ReplicaSetContextCollector()
            pod = _pod(owner_kind="ReplicaSet", owner_name="test-rs")
            result = collector.collect(pod, "default", "test-pod")

        assert result is not None
        assert len(result.context_payload["owner_references"]) == 1
        assert result.context_payload["owner_references"][0]["kind"] == "Deployment"

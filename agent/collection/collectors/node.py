"""Node context collector -- fetches details of the node a pod is scheduled on."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from kubernetes import client
from kubernetes.config.config_exception import ConfigException

from agent.collection.collectors.base import Collector, ContextResult
from agent.common.logging import get_logger

logger = get_logger(__name__)


def _to_iso(value: datetime | str | None) -> str | None:
    """Convert a datetime to an ISO-8601 string, passing strings through."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class NodeContextCollector(Collector):
    """Collector for node-level context of scheduled pods.

    Extracts the node name from the pod spec and fetches the corresponding
    ``Node`` object via the Kubernetes API.
    """

    def __init__(self) -> None:
        """Attempt to configure and initialise the Kubernetes API client."""
        self._api: client.CoreV1Api | None = None
        try:
            try:
                client.config.load_incluster_config()
            except ConfigException:
                client.config.load_kube_config()
            self._api = client.CoreV1Api()
        except Exception:
            logger.exception("Failed to initialise Kubernetes API client")
            self._api = None

    def collect(self, pod: dict, namespace: str, name: str) -> ContextResult | None:
        """Collect node context for a pod.

        Args:
            pod: Pod dict from the Kubernetes API (snake_case keys via
                 ``to_dict()``).
            namespace: The pod's namespace.
            name: The pod's name.

        Returns:
            A ``ContextResult`` with node details, or ``None`` if the pod
            is not scheduled to a node.
        """
        node_name = pod.get("spec", {}).get("node_name")

        if not node_name:
            logger.debug("Pod %s/%s is not scheduled to a node", namespace, name)
            return None

        if self._api is None:
            logger.warning("Kubernetes API client not available")
            return None

        try:
            node = self._api.read_node(name=node_name)
        except Exception:
            logger.exception("Failed to read node %s", node_name)
            return None

        node_dict: dict[str, Any] = node.to_dict()
        metadata = node_dict.get("metadata", {}) or {}
        status = node_dict.get("status", {}) or {}
        node_info = status.get("node_info", {}) or {}

        conditions_raw: list[dict] = status.get("conditions", []) or []
        conditions: list[dict[str, Any]] = [
            {
                "type": c.get("type"),
                "status": c.get("status"),
                "reason": c.get("reason"),
                "message": c.get("message"),
                "last_heartbeat_time": _to_iso(c.get("last_heartbeat_time")),
                "last_transition_time": _to_iso(c.get("last_transition_time")),
            }
            for c in conditions_raw
        ]

        allocatable: dict[str, Any] = dict(status.get("allocatable", {}) or {})
        capacity: dict[str, Any] = dict(status.get("capacity", {}) or {})
        labels: dict[str, str] = dict(metadata.get("labels", {}) or {})

        payload: dict[str, Any] = {
            "name": metadata.get("name"),
            "conditions": conditions,
            "allocatable": allocatable,
            "capacity": capacity,
            "kubelet_version": node_info.get("kubelet_version"),
            "os_image": node_info.get("os_image"),
            "architecture": node_info.get("architecture"),
            "uid": metadata.get("uid"),
            "labels": labels,
        }

        logger.debug(
            "Collected node context for %s (pod %s/%s)",
            payload["name"],
            namespace,
            name,
        )

        return ContextResult(context_type="NODE", context_payload=payload)

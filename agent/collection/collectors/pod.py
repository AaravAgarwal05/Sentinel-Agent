"""Collector for Pod-level context from the Kubernetes API."""

from __future__ import annotations

from typing import Any

from agent.collection.collectors.base import Collector, ContextResult
from agent.common.logging import get_logger

logger = get_logger("agent.collection.collectors.pod")


class PodContextCollector(Collector):
    """Extracts pod metadata, spec, status, and owner references from a pod dict."""

    def collect(
        self, pod: dict, namespace: str, name: str
    ) -> ContextResult | None:
        """Collect context for the given pod.

        Args:
            pod: Pod dict from the Kubernetes API (snake_case keys via
                 ``to_dict()``).
            namespace: The pod's namespace.
            name: The pod's name.

        Returns:
            A ``ContextResult`` with ``context_type="POD"``.
        """
        metadata: dict[str, Any] = pod.get("metadata", {})
        spec: dict[str, Any] = pod.get("spec", {})
        status: dict[str, Any] = pod.get("status", {})

        containers = [
            {
                "name": c.get("name", ""),
                "image": c.get("image", ""),
                "resources": c.get("resources", {}),
            }
            for c in spec.get("containers", [])
        ]

        container_statuses = [
            {
                "name": cs.get("name", ""),
                "state": cs.get("state", {}),
                "ready": cs.get("ready", False),
                "restart_count": cs.get("restart_count", 0),
                "image": cs.get("image", ""),
                "image_id": cs.get("image_id", ""),
                "container_id": cs.get("container_id", ""),
            }
            for cs in status.get("container_statuses", [])
        ]

        conditions = [
            {
                "type": cond.get("type", ""),
                "status": cond.get("status", ""),
                "reason": cond.get("reason", ""),
                "message": cond.get("message", ""),
                "last_transition_time": cond.get("last_transition_time"),
            }
            for cond in status.get("conditions", [])
        ]

        owner_references = [
            {
                "api_version": ref.get("api_version", ""),
                "kind": ref.get("kind", ""),
                "name": ref.get("name", ""),
                "uid": ref.get("uid", ""),
                "controller": ref.get("controller", False),
                "block_owner_deletion": ref.get("block_owner_deletion", False),
            }
            for ref in metadata.get("owner_references") or []
        ]

        return ContextResult(
            context_type="POD",
            context_payload={
                "metadata": {
                    "name": metadata.get("name", ""),
                    "namespace": metadata.get("namespace", ""),
                    "uid": metadata.get("uid", ""),
                    "labels": metadata.get("labels", {}),
                    "annotations": metadata.get("annotations", {}),
                },
                "spec": {
                    "containers": containers,
                    "service_account_name": spec.get("service_account_name", ""),
                    "node_name": spec.get("node_name", ""),
                },
                "status": {
                    "phase": status.get("phase", ""),
                    "conditions": conditions,
                    "container_statuses": container_statuses,
                    "host_ip": status.get("host_ip", ""),
                    "pod_ip": status.get("pod_ip", ""),
                    "qos_class": status.get("qos_class", ""),
                },
                "owner_references": owner_references,
            },
        )

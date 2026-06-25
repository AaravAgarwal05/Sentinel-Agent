"""Namespace context collector for the Sentinel Agent.

Fetches namespace metadata from the Kubernetes API for the namespace
containing the target pod.
"""
from __future__ import annotations

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.config.config_exception import ConfigException

from agent.collection.collectors.base import Collector, ContextResult
from agent.common.logging import get_logger

logger = get_logger(__name__)


class NamespaceContextCollector(Collector):
    """Collector for namespace-level context.

    Fetches metadata (labels, annotations, status phase, UID, creation
    timestamp) from the Kubernetes namespace resource that the target pod
    resides in.
    """

    def __init__(self) -> None:
        """Initialize the collector by loading Kubernetes config and creating
        a CoreV1Api client.
        """
        try:
            k8s_config.load_incluster_config()
        except ConfigException:
            k8s_config.load_kube_config()

        self._api = k8s_client.CoreV1Api()

    def collect(
        self, pod: dict, namespace: str, name: str
    ) -> ContextResult | None:
        """Collect namespace metadata for the given pod's namespace.

        Args:
            pod: Pod dict from the Kubernetes API (snake_case keys via
                 ``to_dict()``).
            namespace: The pod's namespace.
            name: The pod's name (unused here, present for interface
                  conformance).

        Returns:
            A ``ContextResult`` with ``context_type`` ``"NAMESPACE"`` and
            ``context_payload`` containing the namespace name, labels,
            annotations, status phase, UID, and creation timestamp.
        """
        try:
            ns = self._api.read_namespace(name=namespace)
            ns_dict = ns.to_dict()
        except Exception:
            logger.exception("Failed to fetch namespace %s", namespace)
            return ContextResult(
                context_type="NAMESPACE",
                context_payload={
                    "name": namespace,
                    "labels": {},
                    "annotations": {},
                    "status": {"phase": "Unknown"},
                    "uid": "",
                    "creation_timestamp": "",
                },
            )

        metadata = ns_dict.get("metadata", {})
        status = ns_dict.get("status", {})

        creation_timestamp = metadata.get("creation_timestamp")
        creation_timestamp_str = (
            creation_timestamp.isoformat() if creation_timestamp else ""
        )

        return ContextResult(
            context_type="NAMESPACE",
            context_payload={
                "name": metadata.get("name", namespace),
                "labels": metadata.get("labels") or {},
                "annotations": metadata.get("annotations") or {},
                "status": {
                    "phase": status.get("phase", "Unknown"),
                },
                "uid": metadata.get("uid", ""),
                "creation_timestamp": creation_timestamp_str,
            },
        )

"""ReplicaSet context collector for pod-level context enrichment."""

from __future__ import annotations

from typing import Any

from kubernetes import client
from kubernetes.client.rest import ApiException

from agent.collection.collectors.base import Collector, ContextResult
from agent.common.logging import get_logger

logger = get_logger("agent.collection.collectors.replicaset")


class ReplicaSetContextCollector(Collector):
    """Collects ReplicaSet context for pods owned by a ReplicaSet."""

    def __init__(self) -> None:
        self._api: client.AppsV1Api | None = None

    def _get_api(self) -> client.AppsV1Api:
        if self._api is None:
            self._api = client.AppsV1Api()
        return self._api

    def collect(
        self, pod: dict, namespace: str, name: str
    ) -> ContextResult | None:
        """Collect ReplicaSet context if the pod is owned by a ReplicaSet.

        Args:
            pod: Pod dict from the Kubernetes API (snake_case keys via
                 ``to_dict()``).
            namespace: The pod's namespace.
            name: The pod's name (unused but required by the interface).

        Returns:
            A ``ContextResult`` with ReplicaSet details, or ``None`` if the
            pod has no ReplicaSet owner or the ReplicaSet is not found.
        """
        owner_refs = pod.get("metadata", {}).get("owner_references")
        if not owner_refs:
            return None

        # Find the first ReplicaSet owner reference
        rs_ref: dict[str, Any] | None = None
        for ref in owner_refs:
            if ref.get("kind") == "ReplicaSet":
                rs_ref = ref
                break

        if rs_ref is None:
            return None

        rs_name = rs_ref.get("name")
        if not rs_name:
            return None

        try:
            api = self._get_api()
            rs = api.read_namespaced_replica_set(
                name=rs_name, namespace=namespace
            )
        except ApiException as e:
            if e.status == 404:
                logger.debug(
                    "ReplicaSet %s/%s not found for pod %s/%s",
                    namespace,
                    rs_name,
                    namespace,
                    name,
                )
            else:
                logger.warning(
                    "Failed to fetch ReplicaSet %s/%s for pod %s/%s: %s",
                    namespace,
                    rs_name,
                    namespace,
                    name,
                    e,
                )
            return None
        except Exception as e:
            logger.warning(
                "Unexpected error fetching ReplicaSet %s/%s for pod %s/%s: %s",
                namespace,
                rs_name,
                namespace,
                name,
                e,
            )
            return None

        metadata = rs.metadata
        spec = rs.spec
        status = rs.status

        payload: dict[str, Any] = {
            "name": metadata.name if metadata else None,
            "replicas": spec.replicas if spec else None,
            "available_replicas": status.available_replicas if status else None,
            "fully_labeled_replicas": (
                status.fully_labeled_replicas if status else None
            ),
            "owner_references": (
                [
                    ref.to_dict()
                    for ref in (metadata.owner_references or [])
                ]
                if metadata
                else []
            ),
            "uid": metadata.uid if metadata else None,
            "creation_timestamp": (
                metadata.creation_timestamp.isoformat()
                if metadata and metadata.creation_timestamp
                else None
            ),
        }

        return ContextResult(
            context_type="REPLICASET",
            context_payload=payload,
        )

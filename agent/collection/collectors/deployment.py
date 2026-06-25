"""Collector that traces a pod's owner chain to a Deployment."""

from __future__ import annotations

from typing import Any, cast

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from agent.collection.collectors.base import Collector, ContextResult
from agent.common.logging import get_logger

logger = get_logger("agent.collection.collectors.deployment")


class DeploymentContextCollector(Collector):
    """Trace Pod -> ReplicaSet -> Deployment ownership chain."""

    def collect(
        self, pod: dict, namespace: str, name: str  # noqa: ARG002
    ) -> ContextResult | None:
        """Collect Deployment context for the given pod.

        Returns ``None`` when the pod is not owned by a ReplicaSet that is
        itself owned by a Deployment, or when any resource in the chain
        cannot be found.
        """
        apps_api = client.AppsV1Api()

        # ------------------------------------------------------------------
        # Step 1: find the ReplicaSet owner
        # ------------------------------------------------------------------
        rs_name = self._resolve_owner(pod, "ReplicaSet")
        if rs_name is None:
            logger.debug("Pod %s/%s has no ReplicaSet owner", namespace, name)
            return None

        # ------------------------------------------------------------------
        # Step 2: fetch the ReplicaSet and find the Deployment owner
        # ------------------------------------------------------------------
        try:
            rs = apps_api.read_namespaced_replica_set(rs_name, namespace)
        except ApiException as exc:
            if exc.status == 404:
                logger.warning(
                    "ReplicaSet %s/%s not found", namespace, rs_name
                )
                return None
            logger.error(
                "Error fetching ReplicaSet %s/%s: %s",
                namespace,
                rs_name,
                exc,
            )
            return None

        # ReplicaSet .metadata.ownerReferences (via to_dict()) is a list of
        # dicts or None.  The SDK model's to_dict() produces snake_case keys.
        rs_dict = rs.to_dict()
        dep_name = self._resolve_owner(rs_dict, "Deployment")
        if dep_name is None:
            logger.debug(
                "ReplicaSet %s/%s has no Deployment owner", namespace, rs_name
            )
            return None

        # ------------------------------------------------------------------
        # Step 3: fetch the Deployment
        # ------------------------------------------------------------------
        try:
            dep = apps_api.read_namespaced_deployment(dep_name, namespace)
        except ApiException as exc:
            if exc.status == 404:
                logger.warning(
                    "Deployment %s/%s not found", namespace, dep_name
                )
                return None
            logger.error(
                "Error fetching Deployment %s/%s: %s",
                namespace,
                dep_name,
                exc,
            )
            return None

        dep_dict = dep.to_dict()

        # ------------------------------------------------------------------
        # Step 4: build and return the result
        # ------------------------------------------------------------------
        payload: dict[str, Any] = {
            "name": dep_dict["metadata"]["name"],
            "replicas": dep_dict["spec"].get("replicas"),
            "available_replicas": (
                dep_dict.get("status", {}) or {}
            ).get("available_replicas"),
            "strategy": self._extract_strategy(dep_dict),
            "labels": (dep_dict["metadata"].get("labels") or {}).copy(),
            "uid": dep_dict["metadata"]["uid"],
            "creation_timestamp": str(dep_dict["metadata"]["creation_timestamp"]),
        }

        logger.info(
            "Collected Deployment context for pod %s/%s -> %s",
            namespace,
            name,
            dep_name,
        )
        return ContextResult(context_type="DEPLOYMENT", context_payload=payload)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_owner(resource: dict, kind: str) -> str | None:
        """Return the name of the first owner reference matching *kind*, or None."""
        owner_refs = resource.get("metadata", {}).get("owner_references")
        if not owner_refs:
            return None
        for ref in owner_refs:
            if ref.get("kind") == kind:
                return cast(str | None, ref.get("name"))
        return None

    @staticmethod
    def _extract_strategy(dep_dict: dict) -> dict[str, Any]:
        """Extract the deployment strategy as a plain dict."""
        strategy = dep_dict.get("spec", {}).get("strategy") or {}
        result: dict[str, Any] = {}
        # type is always present on a real Deployment spec str.
        strategy_type = strategy.get("type")
        if strategy_type:
            result["type"] = strategy_type

        # RollingUpdate parameters (may not be set for Recreate).
        rolling = strategy.get("rolling_update") or {}
        if rolling:
            ru: dict[str, Any] = {}
            if rolling.get("max_surge") is not None:
                ru["max_surge"] = str(rolling["max_surge"])
            if rolling.get("max_unavailable") is not None:
                ru["max_unavailable"] = str(rolling["max_unavailable"])
            if ru:
                result["rolling_update"] = ru

        return result

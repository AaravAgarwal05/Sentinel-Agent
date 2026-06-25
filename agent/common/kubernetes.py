"""Kubernetes cluster metadata client for the Sentinel Agent."""
from __future__ import annotations

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.config.config_exception import ConfigException


class KubernetesClient:
    """Client for interacting with the Kubernetes API to collect cluster metadata.

    Supports in-cluster configuration (when running inside a pod) and
    local kubeconfig fallback (for development). All methods handle
    failures gracefully by returning None rather than raising.
    """

    def __init__(self) -> None:
        """Initialize the client, attempting in-cluster config first."""
        self._available: bool = False
        self._api: k8s_client.CoreV1Api | None = None
        self._version_api: k8s_client.VersionApi | None = None
        self._load_config()

    def _load_config(self) -> None:
        """Attempt to load Kubernetes configuration.

        Tries in-cluster config first, then falls back to local kubeconfig.
        Sets _available to True if either succeeds.
        """
        try:
            k8s_config.load_incluster_config()
        except ConfigException:
            try:
                k8s_config.load_kube_config()
            except ConfigException:
                self._available = False
                return

        try:
            self._api = k8s_client.CoreV1Api()
            self._version_api = k8s_client.VersionApi()
            self._available = True
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        """Whether the Kubernetes client is properly configured."""
        return self._available

    def get_cluster_version(self) -> str | None:
        """Return the Kubernetes server version (e.g. "1.28.3") or None.

        Uses ``VersionApi`` rather than ``CoreV1Api`` -- ``CoreV1Api``
        does not expose a ``get_code`` method.
        """
        if not self._available or self._version_api is None:
            return None
        try:
            code = self._version_api.get_code()
            return str(code.git_version)
        except Exception:
            return None

    def get_node_count(self) -> int | None:
        """Return the number of nodes in the cluster or None."""
        if not self._available or self._api is None:
            return None
        try:
            node_list = self._api.list_node()
            return len(node_list.items)
        except Exception:
            return None

    def get_namespace_count(self) -> int | None:
        """Return the number of namespaces in the cluster or None."""
        if not self._available or self._api is None:
            return None
        try:
            ns_list = self._api.list_namespace()
            return len(ns_list.items)
        except Exception:
            return None

"""Polling fallback for pod monitoring when the Watch API is unavailable.

Lists pods on a configurable interval and passes them to the detector
registry for evaluation.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from kubernetes import client

from agent.common.logging import get_logger
from agent.detection.detectors.base import DetectorRegistry
from agent.detection.models import IncidentCandidate

_logger = get_logger("agent.detection.polling")


class PodPoller:
    """Periodically lists pods and runs registered detectors.

    Operates on a background thread at a configurable interval.
    """

    def __init__(
        self,
        detector_registry: DetectorRegistry,
        interval_seconds: int = 60,
        namespace: str = "",
        callback: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> None:
        self._detector_registry: DetectorRegistry = detector_registry
        self._interval: int = interval_seconds
        self._namespace: str = namespace
        self._callback: Callable[[list[dict[str, Any]]], None] | None = callback
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._api: client.CoreV1Api = client.CoreV1Api()

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the polling loop in a daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="pod-poller")
        self._thread.start()
        _logger.info("poller_started", interval_seconds=self._interval)

    def stop(self) -> None:
        """Signal the poller to stop."""
        self._running = False
        _logger.info("poller_stopped")

    def poll(self) -> list[dict[str, Any]]:
        """Single poll cycle: list pods -> run detectors -> return candidates."""
        try:
            method = (
                self._api.list_namespaced_pod
                if self._namespace
                else self._api.list_pod_for_all_namespaces
            )
            kwargs: dict[str, Any] = {}
            if self._namespace:
                kwargs["namespace"] = self._namespace
            pod_list = method(**kwargs)
        except Exception:
            _logger.exception("poll_list_pods_failed")
            return []

        candidates: list[dict[str, Any]] = []
        for pod in pod_list.items:
            pod_dict = pod.to_dict()
            results = self._detector_registry.detect_all(pod_dict)
            for c in results:
                candidates.append({
                    "incident_type": c.incident_type,
                    "severity": c.severity.value,
                    "namespace": c.namespace,
                    "resource_kind": c.resource_kind,
                    "resource_name": c.resource_name,
                    "message": c.message,
                })
        return candidates

    def _loop(self) -> None:
        """Polling loop running on background thread."""
        while self._running:
            try:
                candidates = self.poll()
                if candidates and self._callback:
                    self._callback(candidates)
            except Exception:
                _logger.exception("poll_cycle_error")
            time.sleep(self._interval)

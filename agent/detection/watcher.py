"""Kubernetes Watch API engine for pod events.

Long-running stream with automatic reconnect and structured logging.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from kubernetes import client, watch
from kubernetes.client.exceptions import ApiException

from agent.common.logging import get_logger

_logger = get_logger("agent.detection.watcher")


class PodWatcher:
    """Watches Pod resources via the Kubernetes Watch API.

    Calls the provided callback with each raw event dict received from
    the watch stream. Automatically reconnects on failure with backoff.
    """

    def __init__(
        self,
        callback: Callable[[dict[str, Any]], None],
        namespace: str = "",
    ) -> None:
        self._callback: Callable[[dict[str, Any]], None] = callback
        self._namespace: str = namespace
        self._running: bool = False
        self._api: client.CoreV1Api = client.CoreV1Api()

    def start(self) -> None:
        """Begin watching pods. Blocks the calling thread."""
        self._running = True
        backoff = 1
        while self._running:
            try:
                self._stream()
                backoff = 1
            except ApiException as exc:
                _logger.error(
                    "watch_api_error",
                    status=exc.status,
                    reason=exc.reason,
                )
            except Exception:
                _logger.exception("watch_stream_failed")
            if self._running:
                _logger.info("watch_reconnecting_in_seconds", seconds=backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def stop(self) -> None:
        """Signal the watch loop to exit."""
        self._running = False

    def _stream(self) -> None:
        """Open a watch stream and iterate over events."""
        w = watch.Watch()
        _logger.info("watch_started", namespace=self._namespace or "all")
        method = (
            self._api.list_namespaced_pod
            if self._namespace
            else self._api.list_pod_for_all_namespaces
        )
        kwargs: dict[str, Any] = {"timeout_seconds": 300}
        if self._namespace:
            kwargs["namespace"] = self._namespace

        for event in w.stream(method, **kwargs):
            if not self._running:
                break
            try:
                evt = dict(event) if isinstance(event, dict) else {"raw": str(event)}
                obj = evt.get("object")
                if obj is not None and hasattr(obj, "to_dict"):
                    evt["object"] = obj.to_dict()
                self._callback(evt)
            except Exception:
                _logger.exception("watch_callback_error")

"""Collector for Kubernetes events associated with a pod."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from kubernetes import client

from agent.collection.collectors.base import Collector, ContextResult
from agent.common.logging import get_logger

logger = get_logger("agent.collection.collectors.events")


class EventsContextCollector(Collector):
    """Fetches recent events for the resource in namespace."""

    def __init__(self, max_events: int = 20) -> None:
        """Initialize the collector.

        Args:
            max_events: Maximum number of events to return (newest first).
                        Defaults to 20.
        """
        self.max_events = max_events
        self._api = client.CoreV1Api()

    def collect(
        self, pod: dict, namespace: str, name: str
    ) -> ContextResult | None:
        """Collect events for the given pod.

        Args:
            pod: Pod dict from the Kubernetes API (snake_case keys via
                 ``to_dict()``).
            namespace: The pod's namespace.
            name: The pod's name.

        Returns:
            A ``ContextResult`` with ``context_type="EVENTS"``, or ``None``
            if no events are found or the API call fails.
        """
        try:
            event_list = self._api.list_namespaced_events(namespace=namespace)
        except Exception:
            logger.exception("Failed to list events in namespace %s", namespace)
            return None

        # Filter events associated with this pod
        pod_events: list[dict[str, Any]] = []
        for event in event_list.items:
            obj = event.involved_object
            if obj is None or obj.name != name:
                continue

            src = event.source
            pod_events.append({
                "reason": event.reason or "",
                "message": event.message or "",
                "type": event.type or "",
                "last_timestamp": _format_timestamp(event.last_timestamp),
                "first_timestamp": _format_timestamp(event.first_timestamp),
                "count": event.count or 0,
                "source": {
                    "component": (src.component or "") if src else "",
                    "host": (src.host or "") if src else "",
                },
            })

        if not pod_events:
            return None

        # Sort by last_timestamp descending (newest first), then limit
        pod_events.sort(
            key=lambda e: e["last_timestamp"] or "",
            reverse=True,
        )
        pod_events = pod_events[: self.max_events]

        return ContextResult(
            context_type="EVENTS",
            context_payload={"events": pod_events},
        )


def _format_timestamp(ts: datetime | None) -> str | None:
    """Format a datetime to ISO string, or return None if not set."""
    if ts is None:
        return None
    return ts.isoformat()

"""Collector interface for evidence and telemetry collection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from kubernetes import client  # noqa: F401  # available for subclasses
from pydantic import BaseModel

from agent.common.logging import get_logger

logger = get_logger("agent.collection.collectors")


def sanitize_payload(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable types to strings.

    Kubernetes ``to_dict()`` returns ``datetime`` objects for timestamps,
    which the SQLite JSON column cannot serialize. This helper walks
    the value tree and converts any such value to its ISO string
    representation.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: sanitize_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    return obj


class ContextResult(BaseModel):
    context_type: str
    context_payload: dict[str, Any]


class Collector(ABC):
    """Abstract base for pod-level context collectors."""

    @abstractmethod
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
            A ``ContextResult`` if applicable data was found, or ``None``
            if this collector does not apply to the pod.
        """
        ...

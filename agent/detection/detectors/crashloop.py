"""Detects pods stuck in CrashLoopBackOff state."""
from __future__ import annotations

from agent.detection.detectors.base import Detector
from agent.detection.incident import IncidentSeverity
from agent.detection.models import IncidentCandidate


class CrashLoopBackOffDetector(Detector):
    def detect(self, pod: dict) -> IncidentCandidate | None:
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        name = metadata.get("name", "unknown")
        status = pod.get("status", {})
        container_statuses = status.get("container_statuses", []) or []
        for cs in container_statuses:
            state = cs.get("state", {})
            waiting = state.get("waiting") or {}
            if waiting.get("reason") == "CrashLoopBackOff":
                return IncidentCandidate(
                    incident_type="CrashLoopBackOff",
                    severity=IncidentSeverity.CRITICAL,
                    namespace=namespace,
                    resource_kind="Pod",
                    resource_name=name,
                    message=(
                        f"Container {cs.get('name', 'unknown')} "
                        f"in CrashLoopBackOff: {waiting.get('message', '')}"
                    ),
                )
        return None

"""Detects pods stuck in ImagePullBackOff state."""
from __future__ import annotations

from agent.detection.detectors.base import Detector
from agent.detection.incident import IncidentSeverity
from agent.detection.models import IncidentCandidate


class ImagePullBackOffDetector(Detector):
    def detect(self, pod: dict) -> IncidentCandidate | None:
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        name = metadata.get("name", "unknown")
        status = pod.get("status", {})
        container_statuses = status.get("container_statuses", []) or []
        for cs in container_statuses:
            state = cs.get("state", {})
            waiting = state.get("waiting") or {}
            if waiting.get("reason") == "ImagePullBackOff":
                return IncidentCandidate(
                    incident_type="ImagePullBackOff",
                    severity=IncidentSeverity.HIGH,
                    namespace=namespace,
                    resource_kind="Pod",
                    resource_name=name,
                    message=(
                        f"Container {cs.get('name', 'unknown')} "
                        f"in ImagePullBackOff: {waiting.get('message', '')}"
                    ),
                )
        return None

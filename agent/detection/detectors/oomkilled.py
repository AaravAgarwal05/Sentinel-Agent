"""Detects pods that have been OOMKilled."""
from __future__ import annotations

from agent.detection.detectors.base import Detector
from agent.detection.incident import IncidentSeverity
from agent.detection.models import IncidentCandidate


class OOMKilledDetector(Detector):
    def detect(self, pod: dict) -> IncidentCandidate | None:
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        name = metadata.get("name", "unknown")
        status = pod.get("status", {})
        container_statuses = status.get("container_statuses", []) or []
        for cs in container_statuses:
            last_state = cs.get("last_state", {})
            terminated = last_state.get("terminated") or {}
            if terminated.get("reason") == "OOMKilled":
                return IncidentCandidate(
                    incident_type="OOMKilled",
                    severity=IncidentSeverity.HIGH,
                    namespace=namespace,
                    resource_kind="Pod",
                    resource_name=name,
                    message=(
                        f"Container {cs.get('name', 'unknown')} "
                        f"was OOMKilled: {terminated.get('message', '')}"
                    ),
                )
        return None

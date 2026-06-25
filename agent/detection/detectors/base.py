"""Abstract base detector and registry."""
from __future__ import annotations

from abc import ABC, abstractmethod

from agent.common.logging import get_logger
from agent.detection.models import IncidentCandidate

_logger = get_logger("agent.detection.detectors")


class Detector(ABC):
    """All detectors implement this contract.
    detect(pod) returns IncidentCandidate if failure found, else None.
    """

    @abstractmethod
    def detect(self, pod: dict) -> IncidentCandidate | None:
        """Evaluate a pod dict (from Kubernetes API) for failure conditions."""
        ...

class DetectorRegistry:
    """Holds and iterates all registered detectors."""
    def __init__(self) -> None:
        self._detectors: list[Detector] = []

    def register(self, detector: Detector) -> None:
        self._detectors.append(detector)

    @property
    def all(self) -> list[Detector]:
        return list(self._detectors)

    def detect_all(self, pod: dict) -> list[IncidentCandidate]:
        results: list[IncidentCandidate] = []
        for d in self._detectors:
            try:
                candidate = d.detect(pod)
                if candidate is not None:
                    results.append(candidate)
            except Exception:
                _logger.exception("detector_error", detector=type(d).__name__)
        return results

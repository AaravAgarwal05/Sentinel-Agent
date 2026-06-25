"""Tests for all built-in detectors."""
from __future__ import annotations

from agent.detection.detectors.crashloop import CrashLoopBackOffDetector
from agent.detection.detectors.imagepull import ImagePullBackOffDetector
from agent.detection.detectors.oomkilled import OOMKilledDetector
from agent.detection.incident import IncidentSeverity


def _pod(
    name: str = "test-pod",
    namespace: str = "default",
    phase: str = "Running",
    container_statuses: list | None = None,
) -> dict:
    """Build a minimal Kubernetes pod dict matching the API format."""
    status: dict = {"phase": phase}
    if container_statuses is not None:
        status["container_statuses"] = container_statuses
    return {
        "metadata": {"name": name, "namespace": namespace},
        "status": status,
    }


def _container_state_waiting(reason: str, message: str = "") -> dict:
    return {"state": {"waiting": {"reason": reason, "message": message}}}


def _container_last_state_oomkilled(message: str = "") -> dict:
    return {
        "state": {"running": {"started_at": "2024-01-01T00:00:00Z"}},
        "last_state": {
            "terminated": {
                "reason": "OOMKilled",
                "message": message,
                "exitCode": 137,
            }
        },
    }


def _container_healthy(name: str = "container-1") -> dict:
    return {
        "name": name,
        "ready": True,
        "state": {"running": {"started_at": "2024-01-01T00:00:00Z"}},
    }


# ---------------------------------------------------------------------------
# CrashLoopBackOffDetector
# ---------------------------------------------------------------------------


class TestCrashLoopBackOffDetector:
    def test_detect_returns_candidate_for_crashloop(self) -> None:
        detector = CrashLoopBackOffDetector()
        pod = _pod(
            name="crashing-pod",
            container_statuses=[
                _container_state_waiting(
                    reason="CrashLoopBackOff",
                    message="back-off 5m restarting",
                )
            ],
        )

        candidate = detector.detect(pod)
        assert candidate is not None
        assert candidate.incident_type == "CrashLoopBackOff"
        assert candidate.severity == IncidentSeverity.CRITICAL
        assert candidate.namespace == "default"
        assert candidate.resource_name == "crashing-pod"
        assert candidate.resource_kind == "Pod"
        assert "CrashLoopBackOff" in candidate.message

    def test_detect_returns_none_for_healthy_pod(self) -> None:
        detector = CrashLoopBackOffDetector()
        pod = _pod(
            name="healthy-pod",
            container_statuses=[_container_healthy("container-1")],
        )

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_returns_none_for_pod_with_empty_status(self) -> None:
        detector = CrashLoopBackOffDetector()
        pod = {"metadata": {"name": "empty-pod", "namespace": "default"}, "status": {}}

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_returns_none_when_no_container_statuses(self) -> None:
        detector = CrashLoopBackOffDetector()
        pod = _pod(name="no-status-pod")

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_returns_none_for_different_waiting_reason(self) -> None:
        detector = CrashLoopBackOffDetector()
        pod = _pod(
            name="init-pod",
            container_statuses=[
                _container_state_waiting(reason="PodInitializing")
            ],
        )

        candidate = detector.detect(pod)
        assert candidate is None


# ---------------------------------------------------------------------------
# OOMKilledDetector
# ---------------------------------------------------------------------------


class TestOOMKilledDetector:
    def test_detect_returns_candidate_for_oomkilled(self) -> None:
        detector = OOMKilledDetector()
        pod = _pod(
            name="oom-pod",
            container_statuses=[_container_last_state_oomkilled()],
        )

        candidate = detector.detect(pod)
        assert candidate is not None
        assert candidate.incident_type == "OOMKilled"
        assert candidate.severity == IncidentSeverity.HIGH
        assert candidate.namespace == "default"
        assert candidate.resource_name == "oom-pod"
        assert candidate.resource_kind == "Pod"
        assert "OOMKilled" in candidate.message

    def test_detect_returns_none_for_running_pod(self) -> None:
        detector = OOMKilledDetector()
        pod = _pod(
            name="running-pod",
            container_statuses=[_container_healthy("container-1")],
        )

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_returns_none_for_pod_without_last_state(self) -> None:
        detector = OOMKilledDetector()
        pod = _pod(
            name="no-last-state-pod",
            container_statuses=[
                {
                    "name": "container-1",
                    "state": {"running": {"started_at": "2024-01-01T00:00:00Z"}},
                }
            ],
        )

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_returns_none_for_different_terminated_reason(self) -> None:
        detector = OOMKilledDetector()
        pod = _pod(
            name="error-pod",
            container_statuses=[
                {
                    "name": "container-1",
                    "state": {"running": {"started_at": "2024-01-01T00:00:00Z"}},
                    "last_state": {
                        "terminated": {
                            "reason": "Error",
                            "exitCode": 1,
                        }
                    },
                }
            ],
        )

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_returns_none_when_no_container_statuses(self) -> None:
        detector = OOMKilledDetector()
        pod = _pod(name="no-status-pod")

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_uses_namespace_from_metadata(self) -> None:
        detector = OOMKilledDetector()
        pod = _pod(
            name="oom-pod",
            namespace="production",
            container_statuses=[_container_last_state_oomkilled()],
        )

        candidate = detector.detect(pod)
        assert candidate is not None
        assert candidate.namespace == "production"


# ---------------------------------------------------------------------------
# ImagePullBackOffDetector
# ---------------------------------------------------------------------------


class TestImagePullBackOffDetector:
    def test_detect_returns_candidate_for_imagepullbackoff(self) -> None:
        detector = ImagePullBackOffDetector()
        pod = _pod(
            name="pull-fail-pod",
            container_statuses=[
                _container_state_waiting(
                    reason="ImagePullBackOff",
                    message="Back-off pulling image",
                )
            ],
        )

        candidate = detector.detect(pod)
        assert candidate is not None
        assert candidate.incident_type == "ImagePullBackOff"
        assert candidate.severity == IncidentSeverity.HIGH
        assert candidate.namespace == "default"
        assert candidate.resource_name == "pull-fail-pod"
        assert candidate.resource_kind == "Pod"
        assert "ImagePullBackOff" in candidate.message

    def test_detect_returns_none_for_healthy_pod(self) -> None:
        detector = ImagePullBackOffDetector()
        pod = _pod(
            name="healthy-pod",
            container_statuses=[_container_healthy("container-1")],
        )

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_returns_none_when_no_container_statuses(self) -> None:
        detector = ImagePullBackOffDetector()
        pod = _pod(name="no-status-pod")

        candidate = detector.detect(pod)
        assert candidate is None

    def test_detect_returns_none_for_different_waiting_reason(self) -> None:
        detector = ImagePullBackOffDetector()
        pod = _pod(
            name="init-pod",
            container_statuses=[
                _container_state_waiting(reason="ContainerCreating")
            ],
        )

        candidate = detector.detect(pod)
        assert candidate is None

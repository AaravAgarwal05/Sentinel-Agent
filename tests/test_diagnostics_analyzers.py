"""Tests for diagnostic analyzers."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agent.collection.service import IncidentContextPackage
from agent.diagnostics.analyzers.crashloop import CrashLoopAnalyzer
from agent.diagnostics.analyzers.image_pull import ImagePullAnalyzer
from agent.diagnostics.analyzers.oomkilled import OOMKilledAnalyzer


def _make_incident(
    incident_type: str,
    namespace: str = "default",
    resource_name: str = "test-pod",
    **kwargs: Any,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="test-inc-id",
        incident_type=incident_type,
        namespace=namespace,
        resource_name=resource_name,
        **kwargs,
    )


def _make_pod_with_waiting(
    reason: str, message: str = "", restart_count: int = 0
) -> dict[str, Any]:
    return {
        "metadata": {"name": "test-pod", "namespace": "default"},
        "status": {
            "phase": "Pending",
            "container_statuses": [
                {
                    "name": "app",
                    "restart_count": restart_count,
                    "state": {
                        "waiting": {
                            "reason": reason,
                            "message": message,
                        }
                    },
                }
            ],
        },
    }


# ============================================================
# ImagePullAnalyzer Tests
# ============================================================


def test_imagepull_not_found_from_pod_status() -> None:
    pod = _make_pod_with_waiting("ImagePullBackOff", "manifest for image not found")
    incident = _make_incident("ImagePullBackOff")
    context = IncidentContextPackage(incident=incident, pod=pod, events={"events": []})  # type: ignore[arg-type]

    analyzer = ImagePullAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert result.root_cause == "Container image does not exist"
    assert result.confidence >= 0.95
    assert result.analyzer_name == "ImagePullAnalyzer"


def test_imagepull_not_found_from_events() -> None:
    pod = _make_pod_with_waiting("ImagePullBackOff", "")
    incident = _make_incident("ImagePullBackOff")
    context = IncidentContextPackage(
        incident=incident,  # type: ignore[arg-type]
        pod=pod,
        events={
            "events": [
                {
                    "reason": "ErrImagePull",
                    "message": "Error: ImagePullBackOff: image not found",
                    "type": "Warning",
                }
            ]
        },
    )

    analyzer = ImagePullAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert "does not exist" in result.root_cause.lower() or "not found" in result.root_cause.lower()
    assert result.confidence >= 0.90
    assert result.analyzer_name == "ImagePullAnalyzer"


def test_imagepull_auth_failure() -> None:
    pod = _make_pod_with_waiting(
        "ImagePullBackOff", "unauthorized: authentication required"
    )
    incident = _make_incident("ImagePullBackOff")
    context = IncidentContextPackage(incident=incident, pod=pod)  # type: ignore[arg-type]

    analyzer = ImagePullAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert "authentication" in result.root_cause.lower()
    assert result.confidence >= 0.85
    assert result.analyzer_name == "ImagePullAnalyzer"


def test_imagepull_registry_unavailable() -> None:
    pod = _make_pod_with_waiting(
        "ImagePullBackOff",
        "dial tcp: lookup registry.example.com: no such host",
    )
    incident = _make_incident("ImagePullBackOff")
    context = IncidentContextPackage(incident=incident, pod=pod)  # type: ignore[arg-type]

    analyzer = ImagePullAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert "unavailable" in result.root_cause.lower()
    assert result.confidence >= 0.80
    assert result.analyzer_name == "ImagePullAnalyzer"


def test_imagepull_fallback() -> None:
    pod = _make_pod_with_waiting("ImagePullBackOff", "some unknown error occurred")
    incident = _make_incident("ImagePullBackOff")
    context = IncidentContextPackage(incident=incident, pod=pod)  # type: ignore[arg-type]

    analyzer = ImagePullAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert result.confidence == 0.60
    assert result.analyzer_name == "ImagePullAnalyzer"


def test_imagepull_does_not_match_wrong_type() -> None:
    incident = _make_incident("CrashLoopBackOff")
    context = IncidentContextPackage(incident=incident)  # type: ignore[arg-type]
    analyzer = ImagePullAnalyzer()
    result = analyzer.analyze(incident, context)
    assert result is None


def test_imagepull_returns_none_without_pod() -> None:
    incident = _make_incident("ImagePullBackOff")
    context = IncidentContextPackage(incident=incident, pod=None)  # type: ignore[arg-type]
    analyzer = ImagePullAnalyzer()
    result = analyzer.analyze(incident, context)
    assert result is None


# ============================================================
# CrashLoopAnalyzer Tests
# ============================================================


def _make_crashloop_pod(
    restart_count: int = 5, message: str = ""
) -> dict[str, Any]:
    return {
        "metadata": {"name": "test-pod", "namespace": "default"},
        "status": {
            "phase": "Running",
            "container_statuses": [
                {
                    "name": "app",
                    "restart_count": restart_count,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff" if restart_count > 3 else "",
                            "message": message,
                        }
                    },
                }
            ],
        },
    }


def test_crashloop_repeated_crashes() -> None:
    pod = _make_crashloop_pod(restart_count=5)
    incident = _make_incident("CrashLoopBackOff")
    context = IncidentContextPackage(incident=incident, pod=pod)  # type: ignore[arg-type]

    analyzer = CrashLoopAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert "repeatedly" in result.root_cause.lower() or "crash" in result.root_cause.lower()
    assert result.confidence >= 0.85
    assert result.analyzer_name == "CrashLoopAnalyzer"


def test_crashloop_config_issue() -> None:
    pod = _make_crashloop_pod(
        restart_count=1, message="missing environment variable DATABASE_URL"
    )
    incident = _make_incident("CrashLoopBackOff")
    context = IncidentContextPackage(incident=incident, pod=pod)  # type: ignore[arg-type]

    analyzer = CrashLoopAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert "configuration" in result.root_cause.lower()
    assert result.confidence >= 0.75
    assert result.analyzer_name == "CrashLoopAnalyzer"


def test_crashloop_fallback() -> None:
    pod = _make_crashloop_pod(restart_count=1, message="unknown error")
    incident = _make_incident("CrashLoopBackOff")
    context = IncidentContextPackage(incident=incident, pod=pod)  # type: ignore[arg-type]

    analyzer = CrashLoopAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert result.confidence == 0.60
    assert result.analyzer_name == "CrashLoopAnalyzer"


def test_crashloop_does_not_match_wrong_type() -> None:
    incident = _make_incident("OOMKilled")
    context = IncidentContextPackage(incident=incident)  # type: ignore[arg-type]
    analyzer = CrashLoopAnalyzer()
    result = analyzer.analyze(incident, context)
    assert result is None


def test_crashloop_returns_none_without_pod() -> None:
    incident = _make_incident("CrashLoopBackOff")
    context = IncidentContextPackage(incident=incident, pod=None)  # type: ignore[arg-type]
    analyzer = CrashLoopAnalyzer()
    result = analyzer.analyze(incident, context)
    assert result is None


# ============================================================
# OOMKilledAnalyzer Tests
# ============================================================


def _make_oom_pod(terminated_reason: str = "OOMKilled") -> dict[str, Any]:
    return {
        "metadata": {"name": "test-pod", "namespace": "default"},
        "status": {
            "phase": "Running",
            "container_statuses": [
                {
                    "name": "app",
                    "restart_count": 2,
                    "state": {
                        "terminated": {
                            "reason": terminated_reason,
                            "exit_code": 137,
                        }
                    },
                }
            ],
        },
    }


def test_oomkilled_from_container_status() -> None:
    pod = _make_oom_pod()
    incident = _make_incident("OOMKilled")
    context = IncidentContextPackage(incident=incident, pod=pod)  # type: ignore[arg-type]

    analyzer = OOMKilledAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert "memory limit" in result.root_cause.lower()
    assert result.confidence >= 0.95
    assert result.analyzer_name == "OOMKilledAnalyzer"


def test_oomkilled_from_events() -> None:
    pod = _make_oom_pod()
    incident = _make_incident("OOMKilled")
    context = IncidentContextPackage(
        incident=incident,  # type: ignore[arg-type]
        pod=pod,
        events={
            "events": [
                {"reason": "OOMKilled", "message": "memory limit exceeded"}
            ]
        },
    )

    analyzer = OOMKilledAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert "memory limit" in result.root_cause.lower()
    assert result.confidence >= 0.90
    assert result.analyzer_name == "OOMKilledAnalyzer"


def test_oomkilled_includes_node_memory() -> None:
    pod = _make_oom_pod()
    incident = _make_incident("OOMKilled")
    context = IncidentContextPackage(
        incident=incident,  # type: ignore[arg-type]
        pod=pod,
        node={
            "name": "node-1",
            "allocatable": {"memory": "8Gi"},
            "capacity": {"memory": "16Gi"},
        },
    )

    analyzer = OOMKilledAnalyzer()
    result = analyzer.analyze(incident, context)

    assert result is not None
    assert result.evidence is not None
    assert "node" in result.evidence


def test_oomkilled_does_not_match_wrong_type() -> None:
    incident = _make_incident("CrashLoopBackOff")
    context = IncidentContextPackage(incident=incident)  # type: ignore[arg-type]
    analyzer = OOMKilledAnalyzer()
    result = analyzer.analyze(incident, context)
    assert result is None


def test_oomkilled_returns_none_without_pod() -> None:
    incident = _make_incident("OOMKilled")
    context = IncidentContextPackage(incident=incident, pod=None)  # type: ignore[arg-type]
    analyzer = OOMKilledAnalyzer()
    result = analyzer.analyze(incident, context)
    assert result is None

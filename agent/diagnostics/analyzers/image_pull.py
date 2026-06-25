"""Analyzer for ImagePullBackOff incidents."""
from __future__ import annotations

from typing import Any

from agent.common.logging import get_logger
from agent.diagnostics.analyzers.base import DiagnosticAnalyzer, DiagnosticResult

logger = get_logger("agent.diagnostics.analyzers.image_pull")


class ImagePullAnalyzer(DiagnosticAnalyzer):
    """Detects root causes for ImagePullBackOff / ErrImagePull incidents."""

    def analyze(
        self, incident: Any, context_package: Any
    ) -> DiagnosticResult | None:
        if incident.incident_type not in ("ImagePullBackOff", "ErrImagePull"):
            return None

        pod: dict[str, Any] | None = context_package.pod if context_package else None
        events: dict[str, Any] | None = (
            context_package.events if context_package else None
        )

        if pod is None:
            logger.debug("image_pull_analyzer_no_pod_context")
            return None

        # Try each signal pattern
        root_cause, confidence, signals = self._check_image_not_found(pod, events)
        if root_cause:
            return self._make_result(root_cause, confidence, signals, pod, events)

        root_cause, confidence, signals = self._check_auth_failure(pod, events)
        if root_cause:
            return self._make_result(root_cause, confidence, signals, pod, events)

        root_cause, confidence, signals = self._check_registry_unavailable(pod, events)
        if root_cause:
            return self._make_result(root_cause, confidence, signals, pod, events)

        # Fallback
        logger.debug("image_pull_unknown_cause")
        return DiagnosticResult(
            root_cause="Image pull failed — unknown cause",
            confidence=0.60,
            analyzer_name="ImagePullAnalyzer",
        )

    def _make_result(
        self,
        root_cause: str,
        confidence: float,
        signals: list[str],
        pod: dict[str, Any],
        events: dict[str, Any] | None,
    ) -> DiagnosticResult:
        evidence: dict[str, Any] = {
            "signals_used": signals,
            "context_sources": ["pod"],
        }
        if events is not None:
            evidence["context_sources"].append("events")

        # Include container status snapshot
        container_statuses = (
            pod.get("status", {}).get("container_statuses", []) or []
        )
        if container_statuses:
            evidence["container_statuses"] = [
                {
                    "name": cs.get("name"),
                    "restart_count": cs.get("restart_count"),
                    "state": cs.get("state"),
                }
                for cs in container_statuses
            ]

        return DiagnosticResult(
            root_cause=root_cause,
            confidence=confidence,
            analyzer_name="ImagePullAnalyzer",
            evidence=evidence,
        )

    def _check_image_not_found(
        self, pod: dict[str, Any], events: dict[str, Any] | None
    ) -> tuple[str | None, float, list[str]]:
        signals: list[str] = []

        # Check pod container statuses
        container_statuses = (
            pod.get("status", {}).get("container_statuses", []) or []
        )
        for cs in container_statuses:
            state = cs.get("state", {}) or {}
            waiting = state.get("waiting", {}) or {}
            reason = waiting.get("reason", "")
            message = waiting.get("message", "") or ""
            if reason in ("ImagePullBackOff", "ErrImagePull"):
                signals.append(f"container_waiting_reason={reason}")
            if "not found" in message.lower():
                signals.append("image_not_found_in_message")

        # Check events
        if events:
            for evt in events.get("events", []) or []:
                reason = evt.get("reason", "")
                msg = evt.get("message", "") or ""
                if reason in ("ImagePullBackOff", "ErrImagePull"):
                    signals.append(f"event_reason={reason}")
                if "not found" in msg.lower():
                    signals.append("event_image_not_found")

        if signals and (
            "image_not_found_in_message" in signals
            or "event_image_not_found" in signals
        ):
            return "Container image does not exist", 0.97, signals
        return None, 0.0, []

    def _check_auth_failure(
        self, pod: dict[str, Any], events: dict[str, Any] | None
    ) -> tuple[str | None, float, list[str]]:
        signals: list[str] = []
        keywords = [
            "unauthorized", "authentication required",
            "access denied", "authorization failed",
        ]

        container_statuses = (
            pod.get("status", {}).get("container_statuses", []) or []
        )
        for cs in container_statuses:
            state = cs.get("state", {}) or {}
            waiting = state.get("waiting", {}) or {}
            message = waiting.get("message", "") or ""
            for kw in keywords:
                if kw in message.lower():
                    signals.append(f"auth_keyword={kw}")
                    break

        if events:
            for evt in events.get("events", []) or []:
                msg = evt.get("message", "") or ""
                for kw in keywords:
                    if kw in msg.lower():
                        signals.append(f"event_auth_keyword={kw}")
                        break

        if signals:
            return "Container registry authentication failure", 0.92, signals
        return None, 0.0, []

    def _check_registry_unavailable(
        self, pod: dict[str, Any], events: dict[str, Any] | None
    ) -> tuple[str | None, float, list[str]]:
        signals: list[str] = []
        keywords = [
            "timeout", "connection refused", "temporary failure",
            "no such host", "connection reset", "i/o timeout",
        ]

        container_statuses = (
            pod.get("status", {}).get("container_statuses", []) or []
        )
        for cs in container_statuses:
            state = cs.get("state", {}) or {}
            waiting = state.get("waiting", {}) or {}
            message = waiting.get("message", "") or ""
            for kw in keywords:
                if kw in message.lower():
                    signals.append(f"network_keyword={kw}")
                    break

        if events:
            for evt in events.get("events", []) or []:
                msg = evt.get("message", "") or ""
                for kw in keywords:
                    if kw in msg.lower():
                        signals.append(f"event_network_keyword={kw}")
                        break

        if signals:
            return "Container registry unavailable", 0.85, signals
        return None, 0.0, []

"""Analyzer for CrashLoopBackOff incidents."""
from __future__ import annotations

from typing import Any

from agent.common.logging import get_logger
from agent.diagnostics.analyzers.base import DiagnosticAnalyzer, DiagnosticResult

logger = get_logger("agent.diagnostics.analyzers.crashloop")


class CrashLoopAnalyzer(DiagnosticAnalyzer):
    """Detects root causes for CrashLoopBackOff incidents."""

    def analyze(
        self, incident: Any, context_package: Any
    ) -> DiagnosticResult | None:
        if incident.incident_type != "CrashLoopBackOff":
            return None

        pod: dict[str, Any] | None = context_package.pod if context_package else None
        events: dict[str, Any] | None = (
            context_package.events if context_package else None
        )

        if pod is None:
            logger.debug("crashloop_analyzer_no_pod_context")
            return None

        # Check for repeated crashes
        root_cause, confidence, signals = self._check_repeated_crashes(pod, events)
        if root_cause:
            return self._make_result(root_cause, confidence, signals, pod)

        # Check for configuration issue
        root_cause, confidence, signals = self._check_config_issue(pod, events)
        if root_cause:
            return self._make_result(root_cause, confidence, signals, pod)

        # Fallback
        logger.debug("crashloop_unknown_cause")
        return DiagnosticResult(
            root_cause="Container repeatedly crashing — cause unknown",
            confidence=0.60,
            analyzer_name="CrashLoopAnalyzer",
        )

    def _make_result(
        self,
        root_cause: str,
        confidence: float,
        signals: list[str],
        pod: dict[str, Any],
    ) -> DiagnosticResult:
        evidence: dict[str, Any] = {
            "signals_used": signals,
            "context_sources": ["pod"],
        }

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
            analyzer_name="CrashLoopAnalyzer",
            evidence=evidence,
        )

    def _check_repeated_crashes(
        self, pod: dict[str, Any], events: dict[str, Any] | None
    ) -> tuple[str | None, float, list[str]]:
        signals: list[str] = []

        container_statuses = (
            pod.get("status", {}).get("container_statuses", []) or []
        )
        for cs in container_statuses:
            restart_count = cs.get("restart_count", 0) or 0
            if restart_count > 3:
                signals.append(f"restart_count={restart_count}")

            state = cs.get("state", {}) or {}
            waiting = state.get("waiting", {}) or {}
            if waiting.get("reason") == "CrashLoopBackOff":
                signals.append("container_reason=CrashLoopBackOff")

        if events:
            for evt in events.get("events", []) or []:
                if evt.get("reason") == "CrashLoopBackOff":
                    signals.append("event_reason=CrashLoopBackOff")

        if signals:
            return "Application repeatedly crashing during startup", 0.90, signals
        return None, 0.0, []

    def _check_config_issue(
        self, pod: dict[str, Any], events: dict[str, Any] | None
    ) -> tuple[str | None, float, list[str]]:
        signals: list[str] = []
        keywords = [
            "configuration", "config", "missing environment variable",
            "startup failure", "invalid argument", "fatal",
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
                    signals.append(f"config_keyword={kw}")
                    break

        if events:
            for evt in events.get("events", []) or []:
                msg = evt.get("message", "") or ""
                for kw in keywords:
                    if kw in msg.lower():
                        signals.append(f"event_config_keyword={kw}")
                        break

        if signals:
            return "Application configuration error", 0.80, signals
        return None, 0.0, []

"""Analyzer for OOMKilled incidents."""
from __future__ import annotations

from typing import Any

from agent.common.logging import get_logger
from agent.diagnostics.analyzers.base import DiagnosticAnalyzer, DiagnosticResult

logger = get_logger("agent.diagnostics.analyzers.oomkilled")


class OOMKilledAnalyzer(DiagnosticAnalyzer):
    """Detects root causes for OOMKilled incidents."""

    def analyze(
        self, incident: Any, context_package: Any
    ) -> DiagnosticResult | None:
        if incident.incident_type != "OOMKilled":
            return None

        pod: dict[str, Any] | None = context_package.pod if context_package else None
        events: dict[str, Any] | None = (
            context_package.events if context_package else None
        )
        node: dict[str, Any] | None = (
            context_package.node if context_package else None
        )

        if pod is None:
            logger.debug("oomkilled_analyzer_no_pod_context")
            return None

        signals: list[str] = []

        # Check container status for OOMKilled
        container_statuses = (
            pod.get("status", {}).get("container_statuses", []) or []
        )
        for cs in container_statuses:
            state = cs.get("state", {}) or {}
            terminated = state.get("terminated", {}) or {}
            if terminated.get("reason") == "OOMKilled":
                signals.append("container_terminated_reason=OOMKilled")

        # Check events
        if events:
            for evt in events.get("events", []) or []:
                if evt.get("reason") == "OOMKilled":
                    signals.append("event_reason=OOMKilled")
                msg = evt.get("message", "") or ""
                if "memory limit" in msg.lower() or "memory pressure" in msg.lower():
                    signals.append("event_memory_pressure")

        if not signals:
            logger.debug("oomkilled_no_signals")
            return None

        # Build evidence
        evidence: dict[str, Any] = {
            "signals_used": signals,
            "context_sources": ["pod"],
        }
        if events is not None:
            evidence["context_sources"].append("events")
        if node is not None:
            evidence["context_sources"].append("node")
            evidence["node"] = {
                "name": node.get("name"),
                "allocatable": node.get("allocatable"),
                "capacity": node.get("capacity"),
            }

        confidence = 0.98 if any("OOMKilled" in s for s in signals) else 0.90

        return DiagnosticResult(
            root_cause="Container exceeded memory limit",
            confidence=confidence,
            analyzer_name="OOMKilledAnalyzer",
            evidence=evidence,
        )

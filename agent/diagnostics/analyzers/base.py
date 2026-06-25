"""Abstract base class for diagnostic analyzers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from agent.common.logging import get_logger

logger = get_logger("agent.diagnostics.analyzers")


@dataclass
class DiagnosticResult:
    """Structured finding produced by an analyzer."""

    root_cause: str
    confidence: float
    summary: str | None = None
    evidence: dict[str, Any] | None = None
    analyzer_name: str = ""


class DiagnosticAnalyzer(ABC):
    """Analyzes an incident and its collected context to produce a diagnosis."""

    @abstractmethod
    def analyze(
        self, incident: Any, context_package: Any
    ) -> DiagnosticResult | None:
        """Run analysis and return a result, or None if this analyzer does not apply.

        Args:
            incident: The Incident ORM instance.
            context_package: An ``IncidentContextPackage`` with collected context
                from Milestone 3.

        Returns:
            A :class:`DiagnosticResult` if a diagnosis was reached, else ``None``.
        """

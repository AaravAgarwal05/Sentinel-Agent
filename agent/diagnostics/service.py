"""Orchestrates diagnostic analysis for incidents."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.collection.repositories import IncidentContextRepository
from agent.common.logging import get_logger
from agent.diagnostics.analyzers.base import DiagnosticAnalyzer, DiagnosticResult
from agent.diagnostics.analyzers.crashloop import CrashLoopAnalyzer
from agent.diagnostics.analyzers.image_pull import ImagePullAnalyzer
from agent.diagnostics.analyzers.oomkilled import OOMKilledAnalyzer
from agent.diagnostics.models import DiagnosticReport
from agent.diagnostics.repositories import DiagnosticReportRepository
from agent.storage.database import DatabaseManager

if TYPE_CHECKING:
    pass

_logger = get_logger("agent.diagnostics.service")

# Map of incident_type -> analyzer class
_ANALYZER_REGISTRY: dict[str, type[DiagnosticAnalyzer]] = {
    "ImagePullBackOff": ImagePullAnalyzer,
    "ErrImagePull": ImagePullAnalyzer,
    "CrashLoopBackOff": CrashLoopAnalyzer,
    "OOMKilled": OOMKilledAnalyzer,
}


class DiagnosticService:
    """Orchestrates diagnostic analysis for incidents.

    Flow:
    1. Load incident and its collected context
    2. Select analyzer based on incident_type
    3. Run analyzer
    4. Persist DiagnosticReport
    """

    def __init__(self, db: DatabaseManager) -> None:
        """Initialise the service.

        Args:
            db: The shared database manager for persistence.
        """
        self._db: DatabaseManager = db
        self._report_repo: DiagnosticReportRepository = DiagnosticReportRepository(db)
        self._context_repo: IncidentContextRepository = IncidentContextRepository(db)

    def analyze_incident(
        self,
        incident_id: str,
        context_package: Any | None = None,
    ) -> DiagnosticReport | None:
        """Run diagnostics for an incident and persist the report.

        Args:
            incident_id: The ID of the incident to analyse.
            context_package: Optional pre-loaded context package. If ``None``,
                context will be loaded from the database.

        Returns:
            The persisted :class:`DiagnosticReport`, or ``None`` if no analyzer
            matched or analysis failed.
        """
        _logger.info(
            "diagnostic_started",
            incident_id=incident_id,
        )

        try:
            return self._analyze(incident_id, context_package)
        except Exception:
            _logger.exception(
                "diagnostic_failed",
                incident_id=incident_id,
            )
            return None

    def _analyze(
        self,
        incident_id: str,
        context_package: Any | None = None,
    ) -> DiagnosticReport | None:
        """Internal analysis implementation."""
        # Lazy imports to avoid circular dependencies
        from agent.detection.incident import Incident
        from agent.detection.repositories import IncidentRepository

        incident_repo = IncidentRepository(self._db)

        # 1. Load incident
        with self._db.session() as session:
            incident: Incident | None = incident_repo.get_by_id(session, incident_id)
        if incident is None:
            _logger.warning("diagnostic_incident_not_found", incident_id=incident_id)
            return None

        # 2. Get analyzer
        analyzer = self._get_analyzer(incident.incident_type)
        if analyzer is None:
            _logger.info(
                "no_analyzer_for_type",
                incident_id=incident_id,
                incident_type=incident.incident_type,
            )
            return None

        # 3. Load context if not provided
        if context_package is None:
            context_package = self._load_context_for_incident(incident_id)

        # 4. Run analyzer
        result: DiagnosticResult | None = analyzer.analyze(incident, context_package)
        if result is None:
            _logger.info(
                "diagnostic_no_result",
                incident_id=incident_id,
                incident_type=incident.incident_type,
            )
            return None

        # 5. Persist report
        report = DiagnosticReport(
            incident_id=incident_id,
            root_cause=result.root_cause,
            confidence=result.confidence,
            summary=result.summary,
            evidence=result.evidence,
            analyzer_name=result.analyzer_name,
        )
        with self._db.session() as session:
            self._report_repo.create(session, report)

        _logger.info(
            "diagnostic_completed",
            incident_id=incident_id,
            incident_type=incident.incident_type,
            root_cause=result.root_cause,
            confidence=result.confidence,
        )

        return report

    def _get_analyzer(self, incident_type: str) -> DiagnosticAnalyzer | None:
        """Look up and instantiate an analyzer for the given incident type."""
        cls = _ANALYZER_REGISTRY.get(incident_type)
        if cls is None:
            return None
        return cls()

    def _load_context_for_incident(self, incident_id: str) -> Any | None:
        """Load context records from the database and build a context package."""

        with self._db.session() as session:
            records = self._context_repo.get_by_incident(session, incident_id)

        if not records:
            return None

        from agent.collection.service import IncidentContextPackage

        # Build a minimal package from stored context
        pkg = IncidentContextPackage(incident=None)  # type: ignore[arg-type]
        for record in records:
            ctx_type = (
                record.context_type.value
                if hasattr(record.context_type, "value")
                else str(record.context_type)
            )
            ctx_type_lower = ctx_type.lower()
            payload = record.context_payload or {}
            if ctx_type_lower == "pod":
                pkg.pod = payload
            elif ctx_type_lower == "deployment":
                pkg.deployment = payload
            elif ctx_type_lower == "replicaset":
                pkg.replicaset = payload
            elif ctx_type_lower == "namespace":
                pkg.namespace = payload
            elif ctx_type_lower == "events":
                pkg.events = payload
            elif ctx_type_lower == "node":
                pkg.node = payload

        return pkg

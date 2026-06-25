"""Detection service orchestrating watchers, pollers, detectors, and persistence."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from agent.common.logging import get_logger
from agent.config.settings import get_settings
from agent.detection.detectors.base import DetectorRegistry
from agent.detection.detectors.crashloop import CrashLoopBackOffDetector
from agent.detection.detectors.imagepull import ImagePullBackOffDetector
from agent.detection.detectors.oomkilled import OOMKilledDetector
from agent.detection.incident import Incident
from agent.detection.models import IncidentCandidate
from agent.detection.polling import PodPoller
from agent.detection.repositories import IncidentRepository
from agent.detection.watcher import PodWatcher
from agent.storage.database import DatabaseManager

if TYPE_CHECKING:
    from agent.collection.service import CollectionService
    from agent.diagnostics.models import DiagnosticReport
    from agent.diagnostics.service import DiagnosticService
    from agent.transport.service import TransportService

_logger = get_logger("agent.detection.service")


class DetectionService:
    """Orchestrates Kubernetes pod monitoring, detection, and incident persistence.

    Runs the Watch API as primary detection source with polling fallback.
    Deduplicates incidents: same (incident_type, namespace, resource_name)
    for an OPEN incident updates last_seen_at instead of creating new.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db: DatabaseManager = db
        self._settings = get_settings()
        self._registry: DetectorRegistry = DetectorRegistry()
        self._repository: IncidentRepository = IncidentRepository(db)
        self._collection_service: CollectionService | None = (
            self._init_collection_service(db)
        )
        self._diagnostic_service: DiagnosticService | None = None
        self._transport_service: TransportService | None = None
        self._watcher: PodWatcher | None = None
        self._poller: PodPoller | None = None
        self._watcher_thread: threading.Thread | None = None
        self._started: bool = False

        # Register built-in detectors
        self._registry.register(CrashLoopBackOffDetector())
        self._registry.register(OOMKilledDetector())
        self._registry.register(ImagePullBackOffDetector())

    def _init_collection_service(
        self, db: DatabaseManager
    ) -> CollectionService | None:
        """Lazily import and init CollectionService to avoid circular imports."""
        if not self._settings.collection.enabled:
            return None
        from agent.collection.service import CollectionService

        return CollectionService(db)

    def _init_diagnostic_service(self, db: DatabaseManager) -> DiagnosticService | None:
        """Lazily import and init DiagnosticService to avoid circular imports."""
        from agent.diagnostics.service import DiagnosticService as _DiagnosticService

        return _DiagnosticService(db)

    def _init_transport_service(self, db: DatabaseManager) -> TransportService | None:
        """Lazily import and init TransportService to avoid circular imports."""
        if not self._settings.transport.enabled:
            return None
        from agent.transport.service import TransportService as _TransportService

        return _TransportService(db)

    def start(self) -> None:
        """Start the detection engine (watcher + poller)."""
        if self._started:
            return
        settings = get_settings()
        if not settings.detection.enabled:
            _logger.info("detection_disabled")
            return

        _logger.info("detection_starting")

        # Start watcher in background thread
        self._watcher = PodWatcher(callback=self._handle_event)
        self._watcher_thread = threading.Thread(
            target=self._watcher.start, daemon=True, name="pod-watcher"
        )
        self._watcher_thread.start()
        _logger.info("watcher_started")

        # Start poller as fallback
        self._poller = PodPoller(
            detector_registry=self._registry,
            interval_seconds=settings.detection.polling_interval_seconds,
            callback=self.poll_candidates,
        )
        self._poller.start()
        _logger.info("poller_started", interval=settings.detection.polling_interval_seconds)

        self._started = True
        _logger.info("detection_started")

    def stop(self) -> None:
        """Stop the detection engine."""
        if self._watcher:
            self._watcher.stop()
        if self._poller:
            self._poller.stop()
        self._started = False
        _logger.info("detection_stopped")

    @property
    def started(self) -> bool:
        return self._started

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Process a single Watch API event."""
        event_type = event.get("type", "")
        pod = event.get("object", {})
        if not pod or not isinstance(pod, dict):
            _logger.debug("handle_event_skipped_not_dict", type=event_type)
            return

        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        name = metadata.get("name", "")

        if event_type == "DELETED":
            # Pod gone -> resolve related incidents
            self._resolve_pod_incidents(namespace, name)
            return

        # Check pod health status - resolve if healthy, detect if failing
        healthy = self._is_pod_healthy(pod)
        if healthy:
            self._resolve_pod_incidents(namespace, name)
            return

        # Run detectors
        candidates = self._registry.detect_all(pod)
        for candidate in candidates:
            self._persist_or_update(candidate, pod)

    def poll_candidates(self, candidates: list[dict[str, Any]]) -> None:
        """Process candidates from polling fallback."""
        for c in candidates:
            candidate = IncidentCandidate(
                incident_type=c["incident_type"],
                severity=c["severity"],
                namespace=c["namespace"],
                resource_kind=c["resource_kind"],
                resource_name=c["resource_name"],
                message=c["message"],
            )
            self._persist_or_update(candidate)

    def _persist_or_update(
        self, candidate: IncidentCandidate, pod: dict[str, Any] | None = None
    ) -> None:
        """Persist new incident or update existing OPEN one (dedup).

        Args:
            candidate: The incident candidate to persist or update.
            pod: The Kubernetes pod dict associated with the candidate.
                  Passed through to the collection service for context
                  enrichment on new incidents.
        """
        incident: Incident | None = None

        with self._db.session() as session:
            existing = self._repository.find_open_duplicate(
                session,
                incident_type=candidate.incident_type,
                namespace=candidate.namespace,
                resource_name=candidate.resource_name,
            )
            if existing:
                self._repository.update_last_seen(session, existing.id)
                _logger.info(
                    "incident_updated",
                    incident_type=candidate.incident_type,
                    namespace=candidate.namespace,
                    resource_name=candidate.resource_name,
                )
            else:
                incident = Incident(
                    incident_type=candidate.incident_type,
                    severity=candidate.severity,
                    namespace=candidate.namespace,
                    resource_kind=candidate.resource_kind,
                    resource_name=candidate.resource_name,
                    message=candidate.message,
                )
                self._repository.create(session, incident)
                _logger.info(
                    "incident_detected",
                    incident_type=candidate.incident_type,
                    namespace=candidate.namespace,
                    resource_name=candidate.resource_name,
                )

        # Collect context for newly created incidents (outside DB session
        # to avoid nested session/locking issues with SQLite).
        if incident is not None and self._collection_service:
            try:
                self._collection_service.collect_for_incident(incident, pod)
            except Exception:
                _logger.exception(
                    "context_collection_failed",
                    incident_id=incident.id,
                    incident_type=incident.incident_type,
                    resource_name=candidate.resource_name,
                )

        # Run diagnostics for newly created incidents (after context collected)
        if incident is not None:
            if self._diagnostic_service is None:
                self._diagnostic_service = self._init_diagnostic_service(self._db)
            assert self._diagnostic_service is not None  # mypy narrowing
            report: DiagnosticReport | None = None
            try:
                report = self._diagnostic_service.analyze_incident(incident.id)
            except Exception:
                _logger.exception(
                    "diagnostic_failed",
                    incident_id=incident.id,
                    incident_type=incident.incident_type,
                )

            # Enqueue for transport after diagnostics (non-blocking)
            if self._settings.transport.enabled:
                if self._transport_service is None:
                    self._transport_service = self._init_transport_service(self._db)
                if self._transport_service is not None:
                    try:
                        if report is None:
                            # Create a minimal diagnostic report when analysis
                            # could not produce one (e.g. no pod context from poller)
                            from agent.diagnostics.models import DiagnosticReport as _DR
                            report = _DR(
                                incident_id=incident.id,
                                root_cause="Unknown (no diagnostic analysis)",
                                confidence=0.0,
                                summary=f"Auto-generated report for {incident.incident_type}",
                                analyzer_name="FallbackAnalyzer",
                            )
                            with self._db.session() as session:
                                from agent.diagnostics.repositories import DiagnosticReportRepository as _DRR
                                _DRR(self._db).create(session, report)
                        self._transport_service.enqueue(incident, report)
                    except Exception:
                        _logger.exception(
                            "transport_enqueue_failed",
                            incident_id=incident.id,
                            diagnostic_report_id=report.id if report else None,
                        )

    def _resolve_pod_incidents(self, namespace: str, name: str) -> None:
        """Resolve all OPEN incidents for a pod that became healthy."""
        with self._db.session() as session:
            resolved = self._repository.resolve_pod_incidents(session, namespace, name)
            if resolved:
                _logger.info(
                    "incident_resolved",
                    namespace=namespace,
                    resource_name=name,
                    count=resolved,
                )

    def _is_pod_healthy(self, pod: dict) -> bool:
        """Check if pod is in a healthy/ready state."""
        status = pod.get("status", {})
        phase = status.get("phase", "")
        if phase == "Running":
            container_statuses = status.get("container_statuses", []) or []
            for cs in container_statuses:
                if not cs.get("ready", False):
                    return False
            return True
        return phase in ("Succeeded", "")

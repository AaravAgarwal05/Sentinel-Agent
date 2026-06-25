"""Orchestrates outbound delivery of diagnostic reports to SentinelAI."""
from __future__ import annotations

import json
from typing import Any

from agent.common.logging import get_logger
from agent.config.settings import get_settings
from agent.detection.incident import Incident
from agent.diagnostics.models import DiagnosticReport
from agent.storage.database import DatabaseManager
from agent.transport.client import SentinelAIClient
from agent.transport.models import OutboundReport
from agent.transport.repositories import OutboundReportRepository

_logger = get_logger("agent.transport.service")


class TransportService:
    """Manages outbound report creation and delivery.

    Flow:
    1. ``enqueue()`` creates an ``OutboundReport`` record (PENDING).
    2. ``deliver_pending()`` attempts delivery of PENDING reports.
    3. Success → DELIVERED. Failure → retry (via ``RetryService``).

    The service does *not* block diagnostics — ``enqueue()`` is
    synchronous but cheap (a DB insert).
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db: DatabaseManager = db
        self._settings = get_settings()
        self._repo: OutboundReportRepository = OutboundReportRepository(db)
        self._client: SentinelAIClient | None = None

    def _get_client(self) -> SentinelAIClient:
        """Lazy-init the HTTP client from current settings."""
        if self._client is None:
            cfg = self._settings.transport
            self._client = SentinelAIClient(
                base_url=cfg.base_url,
                api_key=cfg.api_key,
                timeout_seconds=cfg.timeout_seconds,
                mock_mode=cfg.mock_mode,
            )
        return self._client

    def enqueue(
        self,
        incident: Incident,
        diagnostic_report: DiagnosticReport,
    ) -> OutboundReport | None:
        """Create a pending outbound report for delivery.

        Args:
            incident: The incident that was detected.
            diagnostic_report: The diagnostic report to deliver.

        Returns:
            The created :class:`OutboundReport`, or ``None`` if transport
            is disabled.
        """
        if not self._settings.transport.enabled:
            return None

        payload = self._build_payload(incident, diagnostic_report)

        report = OutboundReport(
            incident_id=incident.id,
            diagnostic_report_id=diagnostic_report.id,
            payload=json.dumps(payload, default=str),
        )
        with self._db.session() as session:
            self._repo.create(session, report)

        _logger.info(
            "report_enqueued",
            incident_id=incident.id,
            diagnostic_report_id=diagnostic_report.id,
        )
        return report

    def deliver_pending(self, limit: int = 50) -> int:
        """Attempt delivery of all pending outbound reports.

        Args:
            limit: Maximum reports to process (default 50).

        Returns:
            Number of reports processed.
        """
        with self._db.session() as session:
            pending = self._repo.get_pending(session, limit=limit)

        if not pending:
            return 0

        processed = 0
        for report in pending:
            success = self._attempt_delivery(report)
            with self._db.session() as session:
                if success:
                    self._repo.mark_delivered(session, report.id)
                    _logger.info(
                        "report_delivered",
                        incident_id=report.incident_id,
                        diagnostic_report_id=report.diagnostic_report_id,
                        retry_count=report.retry_count,
                    )
                else:
                    new_count = report.retry_count + 1
                    if new_count >= self._settings.transport.max_retries:
                        self._repo.mark_failed(session, report.id)
                        _logger.info(
                            "report_marked_failed",
                            incident_id=report.incident_id,
                            diagnostic_report_id=report.diagnostic_report_id,
                            retry_count=new_count,
                        )
                    else:
                        self._repo.increment_retry(session, report.id)
                        _logger.info(
                            "report_delivery_failed",
                            incident_id=report.incident_id,
                            diagnostic_report_id=report.diagnostic_report_id,
                            retry_count=new_count,
                        )
            processed += 1

        return processed

    def _attempt_delivery(self, report: OutboundReport) -> bool:
        """Attempt to deliver a single report.

        Args:
            report: The outbound report to deliver.

        Returns:
            ``True`` if delivery succeeded, ``False`` otherwise.
        """
        try:
            payload = json.loads(report.payload)
            client = self._get_client()
            result = client.deliver(
                incident_data=payload,
                diagnostic_report_data={},
            )
            return bool(result.get("accepted", False))
        except Exception:
            _logger.exception(
                "report_delivery_failed",
                incident_id=report.incident_id,
                diagnostic_report_id=report.diagnostic_report_id,
                retry_count=report.retry_count,
            )
            return False

    def _build_payload(
        self,
        incident: Incident,
        diagnostic_report: DiagnosticReport,
    ) -> dict[str, Any]:
        """Build a flat delivery payload matching the sentinel-api Incident model.

        Args:
            incident: The incident.
            diagnostic_report: The diagnostic report.

        Returns:
            A flat dict with only the fields sentinel-api expects.
        """
        return {
            "service": incident.resource_name,
            "severity": str(incident.severity),
            "event_type": str(incident.incident_type).lower(),
            "namespace": incident.namespace,
            "message": incident.message,
            "timestamp": (
                incident.first_seen_at.isoformat()
                if incident.first_seen_at
                else None
            ),
        }

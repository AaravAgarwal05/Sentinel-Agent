"""Repository for DiagnosticReport persistence."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.diagnostics.models import DiagnosticReport
from agent.storage.database import DatabaseManager


class DiagnosticReportRepository:
    """Persistence layer for :class:`DiagnosticReport` records."""

    def __init__(self, db: DatabaseManager) -> None:
        """Store a reference to the application-wide :class:`DatabaseManager`.

        Args:
            db: The shared database manager used to obtain sessions.
        """
        self._db: DatabaseManager = db

    def create(
        self, session: Session, report: DiagnosticReport
    ) -> DiagnosticReport:
        """Insert a new diagnostic report.

        Args:
            session: An active SQLAlchemy session.
            report: The :class:`DiagnosticReport` instance to persist.

        Returns:
            The persisted report with its ``id`` and ``created_at`` populated.
        """
        session.add(report)
        session.flush()
        return report

    def get_by_incident(
        self, session: Session, incident_id: str
    ) -> Sequence[DiagnosticReport]:
        """Return all reports for an incident, newest first.

        Args:
            session: An active SQLAlchemy session.
            incident_id: The incident identifier to look up.

        Returns:
            A sequence of :class:`DiagnosticReport` ordered by ``created_at``
            descending.
        """
        stmt = (
            select(DiagnosticReport)
            .where(DiagnosticReport.incident_id == incident_id)
            .order_by(DiagnosticReport.created_at.desc())
        )
        return session.scalars(stmt).all()

    def list_recent(
        self, session: Session, limit: int = 20
    ) -> Sequence[DiagnosticReport]:
        """Return the most recent diagnostic reports across all incidents.

        Args:
            session: An active SQLAlchemy session.
            limit: Maximum number of records to return (default 20).

        Returns:
            A sequence of :class:`DiagnosticReport` ordered by ``created_at``
            descending, limited to ``limit`` entries.
        """
        stmt = (
            select(DiagnosticReport)
            .order_by(DiagnosticReport.created_at.desc())
            .limit(limit)
        )
        return session.scalars(stmt).all()

"""Repository for OutboundReport persistence."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from agent.storage.database import DatabaseManager
from agent.transport.models import OutboundReport, OutboundStatus


class OutboundReportRepository:
    """Persistence layer for :class:`OutboundReport` records."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db: DatabaseManager = db

    def create(
        self, session: Session, report: OutboundReport
    ) -> OutboundReport:
        """Insert a new outbound report.

        Args:
            session: An active SQLAlchemy session.
            report: The :class:`OutboundReport` instance to persist.

        Returns:
            The persisted report with its ``id`` and ``created_at`` populated.
        """
        session.add(report)
        session.flush()
        return report

    def get_pending(
        self, session: Session, limit: int = 50
    ) -> Sequence[OutboundReport]:
        """Return pending outbound reports, oldest first.

        Args:
            session: An active SQLAlchemy session.
            limit: Maximum number of records to return (default 50).

        Returns:
            A sequence of :class:`OutboundReport` with status ``PENDING``
            ordered by ``created_at`` ascending.
        """
        stmt = (
            select(OutboundReport)
            .where(OutboundReport.status == OutboundStatus.PENDING)
            .order_by(OutboundReport.created_at.asc())
            .limit(limit)
        )
        return session.scalars(stmt).all()

    def mark_delivered(
        self, session: Session, report_id: str
    ) -> None:
        """Mark a report as successfully delivered.

        Args:
            session: An active SQLAlchemy session.
            report_id: The ID of the report to mark.
        """
        now = datetime.now(UTC)
        stmt = (
            update(OutboundReport)
            .where(OutboundReport.id == report_id)
            .values(
                status=OutboundStatus.DELIVERED,
                delivered_at=now,
                last_attempt_at=now,
            )
        )
        session.execute(stmt)

    def increment_retry(
        self, session: Session, report_id: str
    ) -> None:
        """Increment retry count and update last_attempt_at.

        Args:
            session: An active SQLAlchemy session.
            report_id: The ID of the report to update.
        """
        now = datetime.now(UTC)
        stmt = (
            update(OutboundReport)
            .where(OutboundReport.id == report_id)
            .values(
                retry_count=OutboundReport.retry_count + 1,
                last_attempt_at=now,
            )
        )
        session.execute(stmt)

    def mark_failed(
        self, session: Session, report_id: str
    ) -> None:
        """Mark a report as permanently failed.

        Args:
            session: An active SQLAlchemy session.
            report_id: The ID of the report to mark.
        """
        now = datetime.now(UTC)
        stmt = (
            update(OutboundReport)
            .where(OutboundReport.id == report_id)
            .values(
                status=OutboundStatus.FAILED,
                last_attempt_at=now,
            )
        )
        session.execute(stmt)

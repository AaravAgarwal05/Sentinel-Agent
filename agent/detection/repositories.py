"""Repository for Incident persistence."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from agent.common.logging import get_logger
from agent.detection.incident import Incident, IncidentStatus
from agent.storage.database import DatabaseManager

_logger = get_logger("agent.detection.repositories")


class IncidentRepository:
    """Persistence layer for Incident records."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db: DatabaseManager = db

    def create(self, session: Session, incident: Incident) -> Incident:
        session.add(incident)
        session.flush()
        return incident

    def get_by_id(self, session: Session, incident_id: str) -> Incident | None:
        stmt = select(Incident).where(Incident.id == incident_id)
        return session.scalar(stmt)

    def list_open(self, session: Session) -> Sequence[Incident]:
        stmt = (
            select(Incident)
            .where(Incident.status == IncidentStatus.OPEN)
            .order_by(Incident.first_seen_at.desc())
        )
        return session.scalars(stmt).all()

    def find_open_duplicate(
        self, session: Session, incident_type: str, namespace: str, resource_name: str
    ) -> Incident | None:
        stmt = (
            select(Incident)
            .where(
                Incident.status == IncidentStatus.OPEN,
                Incident.incident_type == incident_type,
                Incident.namespace == namespace,
                Incident.resource_name == resource_name,
            )
            .limit(1)
        )
        return session.scalar(stmt)

    def mark_resolved(self, session: Session, incident_id: str) -> None:
        stmt = (
            update(Incident)
            .where(Incident.id == incident_id)
            .values(
                status=IncidentStatus.RESOLVED,
                last_seen_at=datetime.now(UTC),
            )
        )
        result = session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"No incident found for id={incident_id!r}")

    def update_last_seen(self, session: Session, incident_id: str) -> None:
        stmt = (
            update(Incident)
            .where(Incident.id == incident_id)
            .values(last_seen_at=datetime.now(UTC))
        )
        session.execute(stmt)

    def resolve_pod_incidents(
        self, session: Session, namespace: str, resource_name: str
    ) -> int:
        stmt = (
            update(Incident)
            .where(
                Incident.namespace == namespace,
                Incident.resource_name == resource_name,
                Incident.status == IncidentStatus.OPEN,
            )
            .values(
                status=IncidentStatus.RESOLVED,
                last_seen_at=datetime.now(UTC),
            )
        )
        result = session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined, no-any-return]

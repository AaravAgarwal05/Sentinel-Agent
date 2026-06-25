"""Repository for IncidentContext persistence."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from agent.collection.models import IncidentContext
from agent.common.logging import get_logger
from agent.storage.database import DatabaseManager

_logger = get_logger("agent.collection.repositories")


class IncidentContextRepository:
    """Persistence layer for IncidentContext records."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db: DatabaseManager = db

    def create(self, session: Session, context: IncidentContext) -> IncidentContext:
        session.add(context)
        session.flush()
        return context

    def get_by_incident(
        self, session: Session, incident_id: str
    ) -> Sequence[IncidentContext]:
        stmt = (
            select(IncidentContext)
            .where(IncidentContext.incident_id == incident_id)
            .order_by(IncidentContext.collected_at)
        )
        return session.scalars(stmt).all()

    def delete_by_incident(self, session: Session, incident_id: str) -> int:
        stmt = delete(IncidentContext).where(
            IncidentContext.incident_id == incident_id
        )
        result = session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined, no-any-return]

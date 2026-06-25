"""SQLAlchemy model for incident context (evidence) persistence."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.detection.incident import Incident
from agent.storage.models import Base


class ContextType(enum.StrEnum):
    POD = "POD"
    DEPLOYMENT = "DEPLOYMENT"
    REPLICASET = "REPLICASET"
    NAMESPACE = "NAMESPACE"
    EVENTS = "EVENTS"
    NODE = "NODE"


class IncidentContext(Base):
    __tablename__ = "incident_context"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_id: Mapped[str] = mapped_column(String(36), ForeignKey("incident.id"), nullable=False, index=True)
    context_type: Mapped[ContextType] = mapped_column(Enum(ContextType), nullable=False)
    context_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    incident: Mapped[Incident] = relationship("Incident")

"""SQLAlchemy model for outbound report delivery tracking."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from agent.storage.models import Base


class OutboundStatus(enum.StrEnum):
    """Delivery status for an outbound report."""

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class OutboundReport(Base):
    """Tracks delivery of a diagnostic report to SentinelAI.

    Each row corresponds to one attempt to deliver a (incident, diagnostic)
    pair. The row starts PENDING, moves to DELIVERED on success or FAILED
    after exhausting retries.
    """

    __tablename__ = "outbound_report"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    incident_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
    diagnostic_report_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OutboundStatus] = mapped_column(
        String(16), nullable=False, default=OutboundStatus.PENDING, index=True
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("status", OutboundStatus.PENDING)
        kwargs.setdefault("retry_count", 0)
        super().__init__(**kwargs)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

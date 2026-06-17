"""SQLAlchemy ORM models for the Sentinel Agent.

Defines the declarative base and all table models used for persisting
cluster identity, credentials, and heartbeat records.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all Sentinel Agent ORM models."""


class ClusterIdentity(Base):
    """Persistent record of a registered Kubernetes cluster.

    Each row corresponds to a unique cluster that the agent has
    registered with. The ``last_seen_at`` column is updated on every
    successful heartbeat to track liveness.
    """

    __tablename__ = "cluster_identity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    cluster_name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    kubernetes_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    namespace_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Credentials(Base):
    """Stored API credentials for communicating with the Sentinel control plane.

    Credentials are rotated periodically; the ``expires_at`` column
    supports expiry-based cleanup via :meth:`CredentialsRepository.delete_expired`.
    """

    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key: Mapped[str] = mapped_column(String(512), nullable=False)
    api_url: Mapped[str] = mapped_column(String(512), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HeartbeatRecord(Base):
    """Log of each heartbeat sent by the agent to the control plane.

    Provides an audit trail for diagnosing connectivity issues and
    measuring heartbeat success rates.
    """

    __tablename__ = "heartbeat_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

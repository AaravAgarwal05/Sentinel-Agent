"""Repository classes for the Sentinel Agent storage layer.

Each repository encapsulates CRUD operations for a single ORM model
and accepts a :class:`DatabaseManager` for session access. Repositories
do not manage transactions themselves -- callers use a ``with db.session()``
block and pass the session to repository methods.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from agent.storage.database import DatabaseManager
from agent.storage.models import ClusterIdentity, Credentials, HeartbeatRecord


class ClusterIdentityRepository:
    """Persistence layer for :class:`ClusterIdentity` records."""

    def __init__(self, db: DatabaseManager) -> None:
        """Store a reference to the application-wide :class:`DatabaseManager`.

        Args:
            db: The shared database manager used to obtain sessions.
        """
        self._db: DatabaseManager = db

    def create(
        self,
        session: Session,
        cluster_id: str,
        cluster_name: str,
        agent_version: str,
        kubernetes_version: str | None = None,
        node_count: int | None = None,
        namespace_count: int | None = None,
    ) -> ClusterIdentity:
        """Insert a new cluster identity record.

        Args:
            session: An active SQLAlchemy session.
            cluster_id: Unique identifier for the cluster.
            cluster_name: Human-readable cluster name.
            agent_version: Version of the Sentinel Agent running on this cluster.
            kubernetes_version: Detected Kubernetes version string, if available.
            node_count: Number of nodes in the cluster, if known.
            namespace_count: Number of namespaces in the cluster, if known.

        Returns:
            The newly created :class:`ClusterIdentity` instance with its
            ``id`` and ``registered_at`` fields populated.

        Raises:
            sqlalchemy.exc.IntegrityError: If a row with the same
                ``cluster_id`` already exists.
        """
        identity = ClusterIdentity(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            agent_version=agent_version,
            kubernetes_version=kubernetes_version,
            node_count=node_count,
            namespace_count=namespace_count,
        )
        session.add(identity)
        session.flush()
        return identity

    def get_by_cluster_id(self, session: Session, cluster_id: str) -> ClusterIdentity | None:
        """Look up a cluster identity by its unique cluster ID.

        Args:
            session: An active SQLAlchemy session.
            cluster_id: The unique cluster identifier to search for.

        Returns:
            The matching :class:`ClusterIdentity` if found, else ``None``.
        """
        stmt = select(ClusterIdentity).where(ClusterIdentity.cluster_id == cluster_id)
        return session.scalar(stmt)

    def update_last_seen(self, session: Session, cluster_id: str) -> None:
        """Update the ``last_seen_at`` timestamp for a cluster identity.

        This is called on every successful heartbeat to track cluster
        liveness. Uses an inline UPDATE to avoid a read-then-write race.

        Args:
            session: An active SQLAlchemy session.
            cluster_id: The unique cluster identifier to update.

        Raises:
            ValueError: If no cluster identity exists with the given ID.
        """
        now = datetime.now(UTC)
        stmt = (
            update(ClusterIdentity)
            .where(ClusterIdentity.cluster_id == cluster_id)
            .values(last_seen_at=now)
        )
        result = session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(
                f"No cluster identity found for cluster_id={cluster_id!r}"
            )


class CredentialsRepository:
    """Persistence layer for :class:`Credentials` records."""

    def __init__(self, db: DatabaseManager) -> None:
        """Store a reference to the application-wide :class:`DatabaseManager`.

        Args:
            db: The shared database manager used to obtain sessions.
        """
        self._db: DatabaseManager = db

    def create(
        self,
        session: Session,
        agent_id: str,
        api_key: str,
        api_url: str,
        expires_at: datetime | None = None,
    ) -> Credentials:
        """Insert a new credentials record.

        Args:
            session: An active SQLAlchemy session.
            agent_id: The agent identity these credentials belong to.
            api_key: The API key or token used for authentication.
            api_url: The base URL of the control plane these credentials
                are valid for.
            expires_at: Optional expiry timestamp after which the
                credentials should no longer be used.

        Returns:
            The newly created :class:`Credentials` instance.
        """
        creds = Credentials(
            agent_id=agent_id,
            api_key=api_key,
            api_url=api_url,
            expires_at=expires_at,
        )
        session.add(creds)
        session.flush()
        return creds

    def get_latest(self, session: Session) -> Credentials | None:
        """Return the most recently created credentials record.

        Args:
            session: An active SQLAlchemy session.

        Returns:
            The latest :class:`Credentials` ordered by ``created_at``
            descending, or ``None`` if no credentials exist.
        """
        stmt = (
            select(Credentials)
            .order_by(Credentials.created_at.desc())
            .limit(1)
        )
        return session.scalar(stmt)

    def delete_expired(self, session: Session) -> int:
        """Remove all credentials whose ``expires_at`` is in the past.

        Args:
            session: An active SQLAlchemy session.

        Returns:
            The number of deleted rows.
        """
        now = datetime.now(UTC)
        stmt = select(Credentials).where(Credentials.expires_at < now)
        expired = session.scalars(stmt).all()
        for cred in expired:
            session.delete(cred)
        session.flush()
        return len(expired)


class HeartbeatRepository:
    """Persistence layer for :class:`HeartbeatRecord` entries."""

    def __init__(self, db: DatabaseManager) -> None:
        """Store a reference to the application-wide :class:`DatabaseManager`.

        Args:
            db: The shared database manager used to obtain sessions.
        """
        self._db: DatabaseManager = db

    def create(
        self,
        session: Session,
        cluster_id: str,
        agent_version: str,
        status: str = "ok",
    ) -> HeartbeatRecord:
        """Record a heartbeat event in the database.

        Args:
            session: An active SQLAlchemy session.
            cluster_id: The cluster that sent the heartbeat.
            agent_version: The agent version at the time of the heartbeat.
            status: Heartbeat status string (e.g. ``"ok"``, ``"failed"``).

        Returns:
            The newly created :class:`HeartbeatRecord` instance.
        """
        record = HeartbeatRecord(
            cluster_id=cluster_id,
            agent_version=agent_version,
            status=status,
        )
        session.add(record)
        session.flush()
        return record

    def get_recent(
        self,
        session: Session,
        cluster_id: str,
        limit: int = 10,
    ) -> Sequence[HeartbeatRecord]:
        """Return the most recent heartbeat records for a cluster.

        Args:
            session: An active SQLAlchemy session.
            cluster_id: The cluster to retrieve heartbeats for.
            limit: Maximum number of records to return (default 10).

        Returns:
            A sequence of :class:`HeartbeatRecord` instances ordered by
            ``sent_at`` descending, limited to ``limit`` entries.
        """
        stmt = (
            select(HeartbeatRecord)
            .where(HeartbeatRecord.cluster_id == cluster_id)
            .order_by(HeartbeatRecord.sent_at.desc())
            .limit(limit)
        )
        return session.scalars(stmt).all()

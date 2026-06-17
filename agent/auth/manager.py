"""Credentials management for the Sentinel Agent."""
from __future__ import annotations

from datetime import UTC, datetime

from agent.common.logging import get_logger
from agent.storage.database import DatabaseManager
from agent.storage.models import Credentials
from agent.storage.repositories import CredentialsRepository

_logger = get_logger("agent.auth.manager")


class CredentialsManager:
    """Manages storage, retrieval, and expiry validation of API credentials.

    Credentials are obtained from the Sentinel control plane during
    registration and are persisted locally. This manager provides
    convenience methods for storing new credentials and checking
    whether the agent is currently authenticated.
    """

    def __init__(self, db: DatabaseManager) -> None:
        """Store dependencies used for credential management.

        Args:
            db: The shared database manager for persistence.
        """
        self._db: DatabaseManager = db
        self._repo: CredentialsRepository = CredentialsRepository(db)

    def store_credentials(
        self,
        agent_id: str,
        api_key: str,
        api_url: str,
        expires_at: datetime | None = None,
    ) -> Credentials:
        """Persist credentials from a registration response.

        Args:
            agent_id: The agent identity these credentials belong to.
            api_key: The API key or token used for authentication.
            api_url: The base URL of the control plane these credentials
                are valid for.
            expires_at: Optional expiry timestamp.

        Returns:
            The newly created :class:`Credentials` instance.
        """
        with self._db.session() as session:
            creds = self._repo.create(
                session=session,
                agent_id=agent_id,
                api_key=api_key,
                api_url=api_url,
                expires_at=expires_at,
            )
        _logger.info("credentials_stored", agent_id=agent_id)
        return creds

    def get_active_credentials(self) -> Credentials | None:
        """Return the latest credentials that haven't expired.

        Returns:
            The most recent non-expired :class:`Credentials` record, or
            ``None`` if no credentials exist or all have expired.
        """
        with self._db.session() as session:
            latest = self._repo.get_latest(session)

        if latest is None:
            _logger.debug("credentials_none_found")
            return None

        if latest.expires_at is not None and latest.expires_at < datetime.now(
            UTC,
        ):
            _logger.info("credentials_expired")
            return None

        return latest

    def is_authenticated(self) -> bool:
        """Check if valid credentials exist and haven't expired.

        Returns:
            ``True`` if the agent has non-expired credentials, ``False``
            otherwise.
        """
        active = self.get_active_credentials()
        return active is not None

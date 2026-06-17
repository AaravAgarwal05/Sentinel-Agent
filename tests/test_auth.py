"""Tests for the credentials manager."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import sleep

import pytest

from agent.auth.manager import CredentialsManager
from agent.config.settings import get_settings
from agent.storage.database import DatabaseManager
from agent.storage.models import Base
from agent.storage.repositories import CredentialsRepository


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests."""
    get_settings.cache_clear()


def _init_db(tmp_path: Path) -> DatabaseManager:
    """Create and initialize a DatabaseManager, creating all tables."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    db = DatabaseManager(db_url)
    db.initialize()
    Base.metadata.create_all(db.engine)
    return db


class TestCredentialsManager:
    def test_store_credentials_persists_a_row(self, tmp_path: Path) -> None:
        """``store_credentials()`` creates a credentials record and
        returns it with an ``id``."""
        db = _init_db(tmp_path)
        mgr = CredentialsManager(db)

        creds = mgr.store_credentials(
            agent_id="agent-1",
            api_key="key-123",
            api_url="https://api.example.com",
        )
        assert creds.id is not None
        assert creds.agent_id == "agent-1"
        assert creds.api_key == "key-123"
        assert creds.api_url == "https://api.example.com"

    def test_get_active_credentials_returns_latest(self, tmp_path: Path) -> None:
        """``get_active_credentials()`` returns the most recently stored
        non-expired credentials."""
        db = _init_db(tmp_path)
        mgr = CredentialsManager(db)

        mgr.store_credentials(
            agent_id="agent-1",
            api_key="key-old",
            api_url="https://api.example.com",
        )
        sleep(1.1)  # Ensure a different created_at timestamp
        mgr.store_credentials(
            agent_id="agent-1",
            api_key="key-new",
            api_url="https://api.example.com",
        )

        active = mgr.get_active_credentials()
        assert active is not None
        assert active.api_key == "key-new"

    def test_get_active_credentials_returns_none_when_empty(
        self, tmp_path: Path,
    ) -> None:
        """``get_active_credentials()`` returns ``None`` when no
        credentials exist."""
        db = _init_db(tmp_path)
        mgr = CredentialsManager(db)

        result = mgr.get_active_credentials()
        assert result is None

    def test_is_authenticated_returns_true_with_valid_creds(
        self, tmp_path: Path,
    ) -> None:
        """``is_authenticated()`` returns ``True`` when valid credentials
        exist."""
        db = _init_db(tmp_path)
        mgr = CredentialsManager(db)

        mgr.store_credentials(
            agent_id="agent-1",
            api_key="key-123",
            api_url="https://api.example.com",
        )

        assert mgr.is_authenticated() is True

    def test_is_authenticated_returns_false_when_no_creds(
        self, tmp_path: Path,
    ) -> None:
        """``is_authenticated()`` returns ``False`` when no credentials
        exist."""
        db = _init_db(tmp_path)
        mgr = CredentialsManager(db)

        assert mgr.is_authenticated() is False

    def test_expired_credentials_are_removed_by_repository(self, tmp_path: Path) -> None:
        """Expired credentials are removed by the repository's
        ``delete_expired`` method."""
        db = _init_db(tmp_path)
        repo = CredentialsRepository(db)

        past = datetime(2020, 1, 1, tzinfo=UTC)
        with db.session() as session:
            repo.create(session=session, agent_id="agent-1", api_key="key-expired",
                        api_url="https://api.example.com", expires_at=past)

        with db.session() as session:
            deleted = repo.delete_expired(session)
            assert deleted == 1

        with db.session() as session:
            assert repo.get_latest(session) is None

    def test_credentials_without_expiry_are_returned(self, tmp_path: Path) -> None:
        """``get_active_credentials()`` returns credentials when
        ``expires_at`` is not set (no expiry)."""
        db = _init_db(tmp_path)
        mgr = CredentialsManager(db)

        mgr.store_credentials(
            agent_id="agent-1",
            api_key="key-valid",
            api_url="https://api.example.com",
        )

        result = mgr.get_active_credentials()
        assert result is not None
        assert result.api_key == "key-valid"
        assert result.expires_at is None

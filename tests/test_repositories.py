"""Tests for the storage repository layer."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import sleep

import pytest
from sqlalchemy import text

from agent.config.settings import get_settings
from agent.storage.database import DatabaseManager
from agent.storage.models import Base
from agent.storage.repositories import (
    ClusterIdentityRepository,
    CredentialsRepository,
    HeartbeatRepository,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests."""
    get_settings.cache_clear()


def _file_url(tmp_path: Path, name: str = "test.db") -> str:
    """Build a ``sqlite:///<abs path>`` URL for a temp file."""
    return f"sqlite:///{tmp_path / name}"


def _init_db(tmp_path: Path) -> DatabaseManager:
    """Create and initialize a DatabaseManager, creating all tables."""
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    Base.metadata.create_all(db.engine)
    return db


# ---------------------------------------------------------------------------
# ClusterIdentityRepository
# ---------------------------------------------------------------------------


class TestClusterIdentityRepository:
    def test_create_inserts_a_row(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = ClusterIdentityRepository(db)
        with db.session() as session:
            identity = repo.create(
                session=session,
                cluster_id="test-cluster-1",
                cluster_name="test-cluster",
                agent_version="1.0.0",
            )
            assert identity.id is not None
            assert identity.cluster_id == "test-cluster-1"
            assert identity.cluster_name == "test-cluster"
            assert identity.agent_version == "1.0.0"

        # Verify it was actually persisted
        with db.session() as session:
            row = session.execute(
                text("SELECT cluster_id FROM cluster_identity WHERE id = :id"),
                {"id": identity.id},
            ).scalar()
            assert row == "test-cluster-1"

    def test_get_by_cluster_id_returns_correct_row(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = ClusterIdentityRepository(db)

        with db.session() as session:
            repo.create(session=session, cluster_id="c1", cluster_name="cluster-one",
                        agent_version="1.0.0")
            repo.create(session=session, cluster_id="c2", cluster_name="cluster-two",
                        agent_version="2.0.0")

        with db.session() as session:
            result = repo.get_by_cluster_id(session, "c2")
            assert result is not None
            assert result.cluster_name == "cluster-two"
            assert result.agent_version == "2.0.0"

    def test_get_by_cluster_id_returns_none_for_missing(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = ClusterIdentityRepository(db)

        with db.session() as session:
            result = repo.get_by_cluster_id(session, "nonexistent")
            assert result is None

    def test_update_last_seen_updates_timestamp(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = ClusterIdentityRepository(db)

        with db.session() as session:
            repo.create(session=session, cluster_id="c1", cluster_name="cluster-one",
                        agent_version="1.0.0")

        original_last_seen: datetime | None
        with db.session() as session:
            identity = repo.get_by_cluster_id(session, "c1")
            assert identity is not None
            original_last_seen = identity.last_seen_at

        with db.session() as session:
            repo.update_last_seen(session, "c1")

        with db.session() as session:
            identity = repo.get_by_cluster_id(session, "c1")
            assert identity is not None
            assert identity.last_seen_at >= original_last_seen

    def test_update_last_seen_raises_for_missing(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = ClusterIdentityRepository(db)

        with db.session() as session:
            with pytest.raises(ValueError, match="No cluster identity found"):
                repo.update_last_seen(session, "nonexistent")


# ---------------------------------------------------------------------------
# CredentialsRepository
# ---------------------------------------------------------------------------


class TestCredentialsRepository:
    def test_create_inserts_a_row(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = CredentialsRepository(db)

        with db.session() as session:
            creds = repo.create(
                session=session,
                agent_id="agent-1",
                api_key="key-123",
                api_url="https://api.example.com",
            )
            assert creds.id is not None
            assert creds.agent_id == "agent-1"
            assert creds.api_key == "key-123"
            assert creds.api_url == "https://api.example.com"

    def test_get_latest_returns_most_recent(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = CredentialsRepository(db)

        with db.session() as session:
            repo.create(session=session, agent_id="agent-1", api_key="key-old",
                        api_url="https://api.example.com")

        sleep(1.1)  # Ensure a different created_at timestamp

        with db.session() as session:
            repo.create(session=session, agent_id="agent-1", api_key="key-new",
                        api_url="https://api.example.com")

        with db.session() as session:
            latest = repo.get_latest(session)
            assert latest is not None
            assert latest.api_key == "key-new"

    def test_get_latest_returns_none_when_empty(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = CredentialsRepository(db)

        with db.session() as session:
            result = repo.get_latest(session)
            assert result is None

    def test_delete_expired_removes_expired_rows(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = CredentialsRepository(db)

        past = datetime(2020, 1, 1, tzinfo=UTC)
        future = datetime(2099, 1, 1, tzinfo=UTC)

        with db.session() as session:
            repo.create(session=session, agent_id="agent-1", api_key="key-expired",
                        api_url="https://api.example.com", expires_at=past)
            repo.create(session=session, agent_id="agent-1", api_key="key-valid",
                        api_url="https://api.example.com", expires_at=future)

        with db.session() as session:
            deleted = repo.delete_expired(session)
            assert deleted == 1

        with db.session() as session:
            remaining = repo.get_latest(session)
            assert remaining is not None
            assert remaining.api_key == "key-valid"


# ---------------------------------------------------------------------------
# HeartbeatRepository
# ---------------------------------------------------------------------------


class TestHeartbeatRepository:
    def test_create_inserts_a_row(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = HeartbeatRepository(db)

        with db.session() as session:
            record = repo.create(
                session=session,
                cluster_id="cluster-1",
                agent_version="1.0.0",
                status="ok",
            )
            assert record.id is not None
            assert record.cluster_id == "cluster-1"
            assert record.agent_version == "1.0.0"
            assert record.status == "ok"

    def test_get_recent_returns_correct_rows_ordered_by_sent_at_desc(
        self, tmp_path: Path,
    ) -> None:
        db = _init_db(tmp_path)
        repo = HeartbeatRepository(db)

        cluster_id = "cluster-1"

        with db.session() as session:
            repo.create(session=session, cluster_id=cluster_id,
                        agent_version="1.0.0", status="ok")
            repo.create(session=session, cluster_id="other-cluster",
                        agent_version="1.0.0", status="ok")

        with db.session() as session:
            records = repo.get_recent(session, cluster_id, limit=10)
            assert len(records) == 1
            assert records[0].cluster_id == cluster_id

        # Add more records for ordering test
        with db.session() as session:
            repo.create(session=session, cluster_id=cluster_id,
                        agent_version="1.0.0", status="ok")
            repo.create(session=session, cluster_id=cluster_id,
                        agent_version="1.0.0", status="warning")

        with db.session() as session:
            records = repo.get_recent(session, cluster_id, limit=10)
            assert len(records) == 3
            # Should be ordered by sent_at descending (most recent first)
            for i in range(len(records) - 1):
                assert records[i].sent_at >= records[i + 1].sent_at

    def test_get_recent_respects_limit(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = HeartbeatRepository(db)
        cluster_id = "cluster-1"

        with db.session() as session:
            for _ in range(5):
                repo.create(session=session, cluster_id=cluster_id,
                            agent_version="1.0.0", status="ok")

        with db.session() as session:
            records = repo.get_recent(session, cluster_id, limit=3)
            assert len(records) == 3

    def test_get_recent_returns_empty_when_no_matches(self, tmp_path: Path) -> None:
        db = _init_db(tmp_path)
        repo = HeartbeatRepository(db)

        with db.session() as session:
            records = repo.get_recent(session, "nonexistent", limit=10)
            assert len(records) == 0

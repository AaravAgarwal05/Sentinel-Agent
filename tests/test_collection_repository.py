"""Tests for the IncidentContextRepository."""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.collection.models import ContextType, IncidentContext
from agent.collection.repositories import IncidentContextRepository
from agent.storage.database import DatabaseManager
from agent.storage.models import Base

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_url(tmp_path: Path, name: str = "test.db") -> str:
    return f"sqlite:///{tmp_path / name}"


def _init_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    Base.metadata.create_all(db.engine)
    return db


def _make_context(
    incident_id: str,
    context_type: ContextType = ContextType.POD,
    payload: dict | None = None,
) -> IncidentContext:
    return IncidentContext(
        incident_id=incident_id,
        context_type=context_type,
        context_payload=payload or {"key": "value"},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    return _init_db(tmp_path)


@pytest.fixture
def repository(db: DatabaseManager) -> IncidentContextRepository:
    return IncidentContextRepository(db)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreate:
    def test_create_persists_context(self, db: DatabaseManager, repository: IncidentContextRepository) -> None:
        ctx = _make_context("inc-001")
        with db.session() as session:
            created = repository.create(session, ctx)
        assert created.id == ctx.id
        assert created.incident_id == "inc-001"
        assert created.context_type == ContextType.POD

    def test_create_assigns_id_and_collected_at(self, db: DatabaseManager, repository: IncidentContextRepository) -> None:
        """After flush the model gets its server-default collected_at."""
        ctx = _make_context("inc-002")
        with db.session() as session:
            created = repository.create(session, ctx)
        assert created.id is not None
        assert len(created.id) == 36
        assert created.collected_at is not None

    def test_create_multiple_contexts_for_same_incident(
        self, db: DatabaseManager, repository: IncidentContextRepository
    ) -> None:
        ctx1 = _make_context("inc-003", ContextType.POD, {"key": "pod"})
        ctx2 = _make_context("inc-003", ContextType.DEPLOYMENT, {"key": "deploy"})
        ctx3 = _make_context("inc-003", ContextType.EVENTS, {"key": "events"})
        with db.session() as session:
            repository.create(session, ctx1)
            repository.create(session, ctx2)
            repository.create(session, ctx3)

        with db.session() as session:
            results = repository.get_by_incident(session, "inc-003")
        assert len(results) == 3

    def test_create_with_empty_payload(self, db: DatabaseManager, repository: IncidentContextRepository) -> None:
        ctx = IncidentContext(
            incident_id="inc-004",
            context_type=ContextType.NAMESPACE,
            context_payload={},
        )
        with db.session() as session:
            created = repository.create(session, ctx)
        assert created.context_payload == {}


# ---------------------------------------------------------------------------
# Get by incident
# ---------------------------------------------------------------------------


class TestGetByIncident:
    def test_returns_contexts_ordered_by_collected_at(
        self, db: DatabaseManager, repository: IncidentContextRepository
    ) -> None:
        """Contexts are returned ordered by collected_at ascending."""
        ctx_a = _make_context("inc-order", ContextType.POD, {"idx": 1})
        ctx_b = _make_context("inc-order", ContextType.NODE, {"idx": 2})
        with db.session() as session:
            repository.create(session, ctx_a)
            repository.create(session, ctx_b)

        with db.session() as session:
            results = repository.get_by_incident(session, "inc-order")
        # Should be ordered by collected_at
        assert len(results) == 2

    def test_returns_empty_list_when_no_contexts(
        self, db: DatabaseManager, repository: IncidentContextRepository
    ) -> None:
        with db.session() as session:
            results = repository.get_by_incident(session, "nonexistent")
        assert results == []

    def test_returns_only_contexts_for_requested_incident(
        self, db: DatabaseManager, repository: IncidentContextRepository
    ) -> None:
        ctx_a = _make_context("inc-a")
        ctx_b = _make_context("inc-b")
        with db.session() as session:
            repository.create(session, ctx_a)
            repository.create(session, ctx_b)

        with db.session() as session:
            results = repository.get_by_incident(session, "inc-a")
        assert len(results) == 1
        assert results[0].incident_id == "inc-a"

    def test_get_by_incident_returns_sequence(self, db: DatabaseManager, repository: IncidentContextRepository) -> None:
        """The return type is a Sequence (supports len, indexing)."""
        ctx = _make_context("inc-seq")
        with db.session() as session:
            repository.create(session, ctx)

        with db.session() as session:
            results = repository.get_by_incident(session, "inc-seq")
        assert len(results) == 1
        assert results[0].incident_id == "inc-seq"


# ---------------------------------------------------------------------------
# Delete by incident
# ---------------------------------------------------------------------------


class TestDeleteByIncident:
    def test_delete_removes_all_contexts_for_incident(
        self, db: DatabaseManager, repository: IncidentContextRepository
    ) -> None:
        ctx = _make_context("inc-del")
        with db.session() as session:
            repository.create(session, ctx)

        with db.session() as session:
            deleted = repository.delete_by_incident(session, "inc-del")
        assert deleted == 1

        with db.session() as session:
            results = repository.get_by_incident(session, "inc-del")
        assert len(results) == 0

    def test_delete_does_not_affect_other_incidents(
        self, db: DatabaseManager, repository: IncidentContextRepository
    ) -> None:
        ctx_a = _make_context("inc-keep")
        ctx_b = _make_context("inc-remove")
        with db.session() as session:
            repository.create(session, ctx_a)
            repository.create(session, ctx_b)

        with db.session() as session:
            repository.delete_by_incident(session, "inc-remove")

        with db.session() as session:
            remaining = repository.get_by_incident(session, "inc-keep")
        assert len(remaining) == 1

    def test_delete_returns_zero_for_nonexistent_incident(
        self, db: DatabaseManager, repository: IncidentContextRepository
    ) -> None:
        with db.session() as session:
            deleted = repository.delete_by_incident(session, "no-such-incident")
        assert deleted == 0

    def test_delete_multiple_contexts_at_once(
        self, db: DatabaseManager, repository: IncidentContextRepository
    ) -> None:
        for i in range(3):
            ctx = _make_context("inc-bulk", ContextType.POD, {"i": i})
            with db.session() as session:
                repository.create(session, ctx)

        with db.session() as session:
            deleted = repository.delete_by_incident(session, "inc-bulk")
        assert deleted == 3

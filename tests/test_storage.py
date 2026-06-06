"""Tests for the database foundation layer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from agent.storage.database import DatabaseManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_url(tmp_path: Path, name: str = "test.db") -> str:
    """Build a ``sqlite:///<abs path>`` URL for a temp file."""
    return f"sqlite:///{tmp_path / name}"


# ---------------------------------------------------------------------------
# DatabaseManager creation
# ---------------------------------------------------------------------------


def test_database_manager_creation_does_not_initialize() -> None:
    """Constructing a DatabaseManager does not create an engine."""
    db = DatabaseManager("sqlite:///:memory:")
    with pytest.raises(RuntimeError, match="not initialized"):
        _ = db.engine


def test_database_manager_access_before_initialize_raises() -> None:
    """Engine and session_factory raise until initialize() is called."""
    db = DatabaseManager("sqlite:///:memory:")
    with pytest.raises(RuntimeError, match="not initialized"):
        _ = db.engine
    with pytest.raises(RuntimeError, match="not initialized"):
        _ = db.session_factory
    with pytest.raises(RuntimeError, match="not initialized"):
        with db.session():
            pytest.fail("session() should not yield before initialize()")


def test_initialize_twice_raises(tmp_path: Path) -> None:
    """``initialize()`` is one-shot; calling it again raises."""
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    with pytest.raises(RuntimeError, match="already initialized"):
        db.initialize()


# ---------------------------------------------------------------------------
# Engine creation
# ---------------------------------------------------------------------------


def test_initialize_creates_engine(tmp_path: Path) -> None:
    """``initialize()`` produces a real SQLAlchemy Engine."""
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    assert isinstance(db.engine, Engine)


def test_initialize_creates_session_factory(tmp_path: Path) -> None:
    """``initialize()`` produces a sessionmaker that yields Sessions."""
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    factory = db.session_factory
    assert isinstance(factory, sessionmaker)
    session = factory()
    assert isinstance(session, Session)
    session.close()


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def test_session_yields_a_usable_session(tmp_path: Path) -> None:
    """The yielded session can execute queries inside the with-block."""
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    with db.session() as session:
        assert isinstance(session, Session)
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_session_propagates_exceptions(tmp_path: Path) -> None:
    """An exception inside the with-block is re-raised to the caller."""
    db = DatabaseManager(_file_url(tmp_path))
    db.initialize()
    with pytest.raises(RuntimeError, match="boom"):
        with db.session() as session:
            session.execute(text("SELECT 1"))
            raise RuntimeError("boom")


def test_session_closes_on_normal_exit() -> None:
    """``close()`` is called when the with-block exits normally."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    mock_session = MagicMock(spec=Session)
    db._session_factory = MagicMock(return_value=mock_session)

    with db.session():
        pass

    mock_session.close.assert_called_once()
    mock_session.rollback.assert_not_called()
    mock_session.commit.assert_called_once()


def test_session_closes_on_exception() -> None:
    """``close()`` is called even when an exception escapes the with-block."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    mock_session = MagicMock(spec=Session)
    db._session_factory = MagicMock(return_value=mock_session)

    with pytest.raises(RuntimeError, match="boom"):
        with db.session():
            raise RuntimeError("boom")

    mock_session.close.assert_called_once()
    mock_session.rollback.assert_called_once()
    mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Commit / rollback behavior
# ---------------------------------------------------------------------------


def test_session_commits_on_normal_exit() -> None:
    """Normal exit of the with-block calls ``commit()`` on the session."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    mock_session = MagicMock(spec=Session)
    db._session_factory = MagicMock(return_value=mock_session)

    with db.session():
        pass

    mock_session.commit.assert_called_once()
    mock_session.rollback.assert_not_called()
    mock_session.close.assert_called_once()


def test_session_rolls_back_on_exception() -> None:
    """An exception inside the with-block triggers ``rollback()``."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    mock_session = MagicMock(spec=Session)
    db._session_factory = MagicMock(return_value=mock_session)

    with pytest.raises(ValueError, match="boom"):
        with db.session():
            raise ValueError("boom")

    mock_session.rollback.assert_called_once()
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()


def test_session_closes_even_when_commit_raises() -> None:
    """``close()`` runs even if ``commit()`` raises."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    mock_session = MagicMock(spec=Session)
    mock_session.commit.side_effect = RuntimeError("commit failed")
    db._session_factory = MagicMock(return_value=mock_session)

    with pytest.raises(RuntimeError, match="commit failed"):
        with db.session():
            pass

    mock_session.close.assert_called_once()

"""Database engine and session factory for the Sentinel Agent.

Phase 2 provides only the database foundation layer -- engine creation,
session factory, and commit/rollback lifecycle. No ORM entities, no
metadata, and no tables are defined here. Schema and entities land in
a future phase; the Alembic infrastructure in ``alembic/`` is what
will own that work.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


class DatabaseManager:
    """Manages the SQLAlchemy engine and session factory for the agent.

    The manager is constructed with a database URL and must be
    :meth:`initialize`d before use. After initialization, it exposes
    the engine, session factory, and a context-managed session that
    handles commit/rollback automatically.

    No tables are created, no ORM entities are defined, and no
    ``metadata.create_all`` is invoked. This is a pure database
    foundation layer.

    Example::

        db = DatabaseManager("sqlite:///./sentinel.db")
        db.initialize()
        with db.session() as session:
            ...
    """

    def __init__(self, database_url: str) -> None:
        self._database_url: str = database_url
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    def initialize(self) -> None:
        """Create the engine and session factory.

        Raises:
            RuntimeError: If the manager has already been initialized.
                Construct a new ``DatabaseManager`` to re-initialize with
                a different URL.
        """
        if self._engine is not None:
            raise RuntimeError("DatabaseManager already initialized")
        self._engine = create_engine(self._database_url)
        self._session_factory = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            class_=Session,
        )

    @property
    def engine(self) -> Engine:
        """Return the SQLAlchemy :class:`~sqlalchemy.Engine`.

        Raises:
            RuntimeError: If the manager has not been initialized.
        """
        if self._engine is None:
            raise RuntimeError(
                "DatabaseManager not initialized; call initialize() first"
            )
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Return the :class:`~sqlalchemy.orm.sessionmaker`.

        Raises:
            RuntimeError: If the manager has not been initialized.
        """
        if self._session_factory is None:
            raise RuntimeError(
                "DatabaseManager not initialized; call initialize() first"
            )
        return self._session_factory

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a :class:`~sqlalchemy.orm.Session` with safe commit/rollback.

        The session is committed on successful exit of the ``with`` block,
        rolled back if an exception is raised, and always closed.
        """
        if self._session_factory is None:
            raise RuntimeError(
                "DatabaseManager not initialized; call initialize() first"
            )
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

"""Local persistence layer for the Sentinel Agent.

Phase 2 ships only the database foundation -- engine, session factory,
and Alembic scaffolding. No tables, models, or repositories exist yet.
"""

from agent.storage.database import DatabaseManager

__all__ = ["DatabaseManager"]

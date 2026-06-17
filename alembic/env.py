"""Alembic migration environment for the Sentinel Agent.

Reads the database URL from the application configuration
(``Settings().storage.database_url``) so the application and
migrations stay in lockstep. ``target_metadata`` is wired to
``Base.metadata`` from :mod:`agent.storage.models` to support
autogenerate.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from agent.config.settings import get_settings
from agent.storage.models import Base
from alembic import context

# Alembic Config object -- provides access to values in alembic.ini.
config = context.config

# Override the URL with the application's configured value. Doing it
# here (rather than in alembic.ini) means deployments only need to
# configure one place for the database URL.
config.set_main_option("sqlalchemy.url", get_settings().storage.database_url)

# Configure Python logging from the ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ORM metadata for autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL to script output rather than executing it against a
    live database. Useful for generating DDL for review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

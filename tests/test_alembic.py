"""Tests for the Alembic infrastructure."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config

from agent.config.settings import get_settings
from alembic import command

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on ``get_settings`` between tests so env vars
    are re-read on every Settings() construction."""
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------


def test_alembic_ini_exists() -> None:
    """The alembic.ini configuration file is checked into the repo."""
    assert ALEMBIC_INI.is_file(), f"missing alembic.ini at {ALEMBIC_INI}"


def test_alembic_config_loads() -> None:
    """``alembic.ini`` is parseable and exposes the expected sections."""
    cfg = Config(str(ALEMBIC_INI))
    # ``Config`` resolves ``script_location`` to an absolute path
    # relative to the ini file's location.
    assert cfg.get_main_option("script_location", default="").endswith("alembic")
    assert cfg.get_main_option("prepend_sys_path") == "."


def test_alembic_versions_directory_exists() -> None:
    """The ``alembic/versions`` directory exists, ready for future migrations."""
    versions_dir = REPO_ROOT / "alembic" / "versions"
    assert versions_dir.is_dir()


def test_alembic_env_py_wires_to_settings() -> None:
    """``alembic/env.py`` reads the URL from the application settings."""
    env_py = (REPO_ROOT / "alembic" / "env.py").read_text()
    assert "from agent.config.settings import get_settings" in env_py
    assert "storage.database_url" in env_py
    assert "run_migrations_offline" in env_py
    assert "run_migrations_online" in env_py


# ---------------------------------------------------------------------------
# End-to-end alembic upgrade head
# ---------------------------------------------------------------------------


def test_alembic_upgrade_head_runs_against_temp_sqlite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``alembic upgrade head`` succeeds against a temp SQLite database.

    The URL is read from ``SENTINEL_STORAGE_DATABASE_URL``, demonstrating
    that env.py is wired to the application configuration rather than
    a hard-coded value in alembic.ini.
    """
    db_path = tmp_path / "sentinel.db"
    monkeypatch.setenv("SENTINEL_STORAGE_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")

    # The database file was created and alembic stamped its version table.
    assert db_path.is_file()

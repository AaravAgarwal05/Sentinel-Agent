# Sentinel Agent

A Kubernetes runtime security agent that performs detection, evidence collection, diagnostics, and remediation across a cluster.

## Current Phase

**Phase 2 — Database Foundation**

Phase 1 introduced a hierarchical configuration system. Phase 2 adds the SQLAlchemy and Alembic foundation — `StorageConfig`, `DatabaseManager`, and Alembic scaffolding — that future phases will use to introduce ORM entities and migrations. No tables, models, repositories, or migrations exist yet; this phase is a pure database plumbing layer.

## Directory Structure

```
sentinel-agent/
├── src/
│   ├── __init__.py
│   └── main.py                  # Entry point: python -m src.main
├── agent/
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   └── logging.py           # structlog JSON logging
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Hierarchical pydantic-settings
│   ├── storage/
│   │   ├── __init__.py
│   │   └── database.py          # DatabaseManager
│   ├── registration/            # Phase N+
│   ├── auth/                    # Phase N+
│   ├── heartbeat/               # Phase N+
│   ├── detection/               # Phase N+
│   ├── collection/              # Phase N+
│   ├── diagnostics/             # Phase N+
│   ├── transport/               # Phase N+
│   ├── execution/               # Phase N+
│   ├── leader/                  # Phase N+
│   └── runtime/
│       ├── __init__.py
│       └── bootstrap.py         # BootstrapManager
├── alembic/
│   ├── env.py                   # Reads URL from settings.storage.database_url
│   ├── script.py.mako
│   ├── README
│   └── versions/                # Migration files (none yet)
├── alembic.ini
├── tests/
│   ├── test_settings.py
│   ├── test_bootstrap.py
│   ├── test_storage.py
│   └── test_alembic.py
├── charts/
│   └── sentinel-agent/          # Helm chart (Phase N+)
├── pyproject.toml
├── poetry.lock
├── Dockerfile
├── .gitignore
└── README.md
```

## Configuration

Settings are organized into five nested Pydantic models and loaded from environment variables prefixed with `SENTINEL_`. There is no file-based loader in this phase.

### Access

```python
from agent.config.settings import get_settings

settings = get_settings()
settings.agent.cluster_name
settings.sentinel.api_url
settings.heartbeat.interval_seconds
settings.runtime.log_level
settings.storage.database_url
```

`get_settings()` is process-wide cached, so the result is safe to call from anywhere. Pass an explicit `Settings(...)` instance to `BootstrapManager` (or any other consumer) to override the cache for a single test or call site.

### Domains

**`AgentConfig`** — identity and deployment metadata for the agent instance.

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `name` | `str` | `"sentinel-agent"` | — |
| `version` | `str` | `"0.1.0"` | — |
| `cluster_name` | `str` | `"default"` | — |
| `environment` | `Literal[...]` | `"development"` | one of `development`, `staging`, `production` |

**`SentinelConfig`** — connection details for the Sentinel control plane.

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `api_url` | `str` | `"https://api.sentinel.example.com"` | non-empty |
| `registration_token` | `str` | `""` | — |

**`HeartbeatConfig`** — heartbeat transmission settings.

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `interval_seconds` | `int` | `30` | `> 0` |

**`RuntimeConfig`** — runtime behavior settings for the agent process.

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `log_level` | `Literal[...]` | `"INFO"` | one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

**`StorageConfig`** — local persistence layer connection settings.

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `database_url` | `str` | `"sqlite:///./sentinel_agent.db"` | non-empty |

### Environment Variables

Environment variables follow the convention `SENTINEL_<DOMAIN>_<FIELD>`. A custom env source maps them into the nested structure, so an unknown `SENTINEL_*` variable is ignored.

| Variable | Maps To | Default |
| --- | --- | --- |
| `SENTINEL_AGENT_NAME` | `settings.agent.name` | `sentinel-agent` |
| `SENTINEL_AGENT_VERSION` | `settings.agent.version` | `0.1.0` |
| `SENTINEL_AGENT_CLUSTER_NAME` | `settings.agent.cluster_name` | `default` |
| `SENTINEL_AGENT_ENVIRONMENT` | `settings.agent.environment` | `development` |
| `SENTINEL_SENTINEL_API_URL` | `settings.sentinel.api_url` | `https://api.sentinel.example.com` |
| `SENTINEL_SENTINEL_REGISTRATION_TOKEN` | `settings.sentinel.registration_token` | `""` |
| `SENTINEL_HEARTBEAT_INTERVAL_SECONDS` | `settings.heartbeat.interval_seconds` | `30` |
| `SENTINEL_RUNTIME_LOG_LEVEL` | `settings.runtime.log_level` | `INFO` |
| `SENTINEL_STORAGE_DATABASE_URL` | `settings.storage.database_url` | `sqlite:///./sentinel_agent.db` |

### Example

```bash
export SENTINEL_AGENT_NAME=cluster-agent
export SENTINEL_AGENT_CLUSTER_NAME=prod-cluster-1
export SENTINEL_AGENT_ENVIRONMENT=production
export SENTINEL_SENTINEL_API_URL=https://api.sentinel.example.com
export SENTINEL_SENTINEL_REGISTRATION_TOKEN=changeme
export SENTINEL_HEARTBEAT_INTERVAL_SECONDS=15
export SENTINEL_RUNTIME_LOG_LEVEL=DEBUG
export SENTINEL_STORAGE_DATABASE_URL=postgresql+psycopg://user:pass@db:5432/sentinel
poetry run python -m src.main
```

Invalid values (empty `api_url`, `interval_seconds <= 0`, an unknown `environment`, an unknown `log_level`, non-numeric `interval_seconds`) raise a Pydantic `ValidationError` at startup rather than being silently coerced.

## Database

Phase 2 provides a database foundation layer — a `DatabaseManager` for the application and Alembic scaffolding for schema migrations. Neither creates tables, models, or migrations yet; that's the work of a future phase.

### `DatabaseManager`

`DatabaseManager` is the only way the rest of the application should talk to SQLAlchemy. It is constructed with a database URL and must be `initialize()`d before use. After initialization it exposes:

- `db.engine` — a SQLAlchemy `Engine`
- `db.session_factory` — a `sessionmaker[Session]`
- `db.session()` — a context-managed `Session` that commits on success, rolls back on exception, and always closes

```python
from agent.storage.database import DatabaseManager

db = DatabaseManager("sqlite:///./sentinel_agent.db")
db.initialize()

with db.session() as session:
    # use session ...
    ...

# `db.engine` and `db.session_factory` are also available
# for callers that need finer control.
```

The bootstrap manager does **not** initialize the database on startup; callers own the lifecycle.

### Alembic

The `alembic/` directory and `alembic.ini` at the project root form a complete Alembic environment. The migration URL is read from `Settings().storage.database_url` at runtime, so the application and migrations share a single source of truth (configure the URL via `SENTINEL_STORAGE_DATABASE_URL`).

```bash
# Create a new revision (future phase)
poetry run alembic revision -m "describe the change"

# Apply pending revisions
poetry run alembic upgrade head

# Roll back one revision
poetry run alembic downgrade -1
```

No migration files exist yet. `alembic upgrade head` against an empty `alembic/versions/` directory is a no-op that succeeds cleanly.

## How to Run

```bash
poetry install
poetry run python -m src.main
```

Sample output (formatted for readability — actual output is single-line JSON):

```json
{
  "timestamp": "2026-06-06T12:34:56.789012Z",
  "level": "info",
  "logger": "agent.runtime.bootstrap",
  "event": "Sentinel Agent starting",
  "agent_name": "sentinel-agent",
  "agent_version": "0.1.0",
  "environment": "development",
  "log_level": "INFO",
  "cluster_name": "default"
}
```

## How to Test

```bash
poetry run pytest
```

## Code Quality

```bash
poetry run ruff check .
poetry run mypy agent src tests
```

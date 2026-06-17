# Sentinel Agent

A Kubernetes runtime security agent that performs detection, evidence collection, diagnostics, and remediation across a cluster.

## Current Phase

**Milestone 1 — Agent Connectivity MVP**

Phase 1 introduced a hierarchical configuration system. Phase 2 added the SQLAlchemy and Alembic foundation. Milestone 1 delivers the connectivity layer: registration with the Sentinel control plane, periodic heartbeats, credential management, and a Kubernetes metadata client. It adds three ORM models (`ClusterIdentity`, `Credentials`, `HeartbeatRecord`), their repositories, an Alembic migration that creates the corresponding tables, and a mock mode that lets the agent operate without a live control plane during development.

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
│   │   ├── logging.py           # structlog JSON logging
│   │   └── kubernetes.py        # Kubernetes cluster metadata client
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Hierarchical pydantic-settings
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py          # DatabaseManager
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   └── repositories.py      # CRUD repositories
│   ├── registration/            # Agent registration with control plane
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── client.py            # HTTP registration client
│   │   └── service.py           # Registration orchestrator
│   ├── auth/
│   │   ├── __init__.py
│   │   └── manager.py           # CredentialsManager
│   ├── heartbeat/               # Periodic health signals
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── client.py            # HTTP heartbeat client
│   │   ├── service.py           # Heartbeat payload builder
│   │   └── scheduler.py         # APScheduler wrapper
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
│   └── versions/
│       └── 0001_add_connectivity_tables.py
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

Settings are organized into five nested Pydantic models and loaded from environment variables prefixed with `SENTINEL_`. There is no file-based loader in this milestone.

### Access

```python
from agent.config.settings import get_settings

settings = get_settings()
settings.agent.cluster_name
settings.sentinel.api_url
settings.sentinel.mock_mode
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
| `mock_mode` | `bool` | `true` | — |
| `mock_mode` | `bool` | `true` | — |

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
| `SENTINEL_SENTINEL_MOCK_MODE` | `settings.sentinel.mock_mode` | `true` |
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

The agent uses SQLAlchemy with Alembic for schema management. Three tables are defined and created by the migration `0001_add_connectivity_tables.py`:

| Table | Purpose |
| --- | --- |
| `cluster_identity` | One row per registered cluster, tracks registration metadata and last-seen timestamp |
| `credentials` | API keys issued by the control plane, with optional expiry |
| `heartbeat_record` | Audit log of every heartbeat sent |

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
```

### `ClusterIdentityRepository`, `CredentialsRepository`, `HeartbeatRepository`

Each repository encapsulates CRUD for its model. Repositories accept a `session` from the caller rather than managing transactions themselves:

```python
from agent.storage.repositories import HeartbeatRepository

repo = HeartbeatRepository(db)
with db.session() as session:
    repo.create(session, cluster_id="…", agent_version="0.1.0")
    recent = repo.get_recent(session, cluster_id="…", limit=5)
```

### Alembic

The `alembic/` directory and `alembic.ini` form a complete Alembic environment. The migration URL is read from `Settings().storage.database_url` at runtime, and `target_metadata` is wired to `Base.metadata` for autogenerate support.

```bash
# Create a new revision
poetry run alembic revision --autogenerate -m "describe the change"

# Apply pending revisions
poetry run alembic upgrade head

# Roll back one revision
poetry run alembic downgrade -1
```

To apply migrations against a temporary SQLite database:

```bash
export SENTINEL_STORAGE_DATABASE_URL=sqlite:///./dev.db
poetry run alembic upgrade head
```

## Registration Flow

When the agent starts, it registers with the Sentinel control plane so the control plane knows the cluster exists and can issue API credentials.

```
                    ┌───────────────────────┐
                    │  RegistrationService   │
                    │  .register()           │
                    └───────┬───────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
     ┌────────────┐ ┌────────────┐ ┌──────────────┐
     │Kubernetes  │ │Registration│ │   Storage    │
     │Client      │ │Client      │ │ (repos)      │
     └────────────┘ └────────────┘ └──────────────┘
```

The flow:

1. **Collect cluster metadata** — the `KubernetesClient` queries the Kubernetes API for server version, node count, and namespace count. If the client is unavailable (e.g., running outside a cluster), these fields are set to `None`.
2. **Generate a cluster ID** — a new UUID is generated for the cluster identity.
3. **Build payload** — a `RegistrationPayload` is assembled with cluster metadata and the registration token from settings.
4. **Send registration** — `RegistrationClient` POSTs to `{api_url}/agent/register` with a Bearer token.
5. **Persist results** — on success, a `ClusterIdentity` and `Credentials` record are written to the database.

In mock mode, step 4 is skipped and a fake `RegistrationResponse` is returned with a `mock-agent-*` prefix.

```python
from agent.common.kubernetes import KubernetesClient
from agent.registration.service import RegistrationService
from agent.storage.database import DatabaseManager

db = DatabaseManager("sqlite:///./sentinel_agent.db")
db.initialize()

k8s = KubernetesClient()                     # may be unavailable
service = RegistrationService(db, k8s)
response = service.register()
```

## Heartbeat Flow

After registration, the agent sends periodic heartbeats to signal liveness to the control plane.

```
  ┌──────────────────┐
  │ HeartbeatScheduler│  (APScheduler)
  │  .start()         │
  └──────┬───────────┘
         │  every interval_seconds
         ▼
  ┌──────────────────┐
  │ HeartbeatService  │
  │ .send_heartbeat() │
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────┐
  │ HeartbeatClient   │  POST /agent/heartbeat
  │ .send(payload)    │
  └──────────────────┘
```

The `HeartbeatScheduler` wraps an APScheduler `BackgroundScheduler`. On `start()` it schedules a recurring job at `settings.heartbeat.interval_seconds`. Each tick:

1. Builds a `HeartbeatPayload` with the current `cluster_id`, `agent_version`, and status.
2. Sends it via `HeartbeatClient.send()`.
3. In mock mode the tick is logged but no HTTP call is made.

```python
from agent.heartbeat.scheduler import HeartbeatScheduler

scheduler = HeartbeatScheduler(cluster_id="my-cluster-uuid")
scheduler.start()
# ... agent runs ...
scheduler.stop()
```

## Mock Mode

When `SENTINEL_SENTINEL_MOCK_MODE=true` (the default), the agent operates without a live Sentinel control plane:

- **Registration** — `RegistrationClient.register()` returns a synthetic `RegistrationResponse` with a `mock-agent-*` agent ID and `mock-api-key-*` key. The full registration flow (metadata collection, payload assembly, local persistence) still executes.
- **Heartbeat** — `HeartbeatClient.send()` logs the payload and returns `True`. `HeartbeatScheduler._tick()` logs the tick and returns without making an HTTP call.

Mock mode is designed for local development and CI. Set `SENTINEL_SENTINEL_MOCK_MODE=false` to connect to a real control plane.

## Runtime Startup Sequence

The `BootstrapManager` is the lifecycle entry point called from `src/main.py`. Its `start()` method performs the initial startup work:

1. **Configure logging** — structlog is configured with the requested log level.
2. **Emit startup event** — a JSON line with agent identity metadata is written to stdout.

Future milestones will extend `BootstrapManager` to chain additional steps: initialize the database, register with the control plane, persist credentials, and start the heartbeat scheduler. The full eventual sequence is:

```
bootstrap → DB init → K8s client → registration → credentials → heartbeat
```

For now `start()` handles only logging and startup events; downstream callers own the rest of the lifecycle.

```python
from agent.runtime.bootstrap import BootstrapManager

bootstrap = BootstrapManager()
bootstrap.start()
```

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

## Deployment

### Docker

To build and run:

```bash
docker build -t sentinel-agent .
docker run --rm sentinel-agent
```

Pass environment variables with `-e`:

```bash
docker run --rm \
  -e SENTINEL_SENTINEL_MOCK_MODE=false \
  -e SENTINEL_SENTINEL_API_URL=https://your-sentinel-instance.example.com \
  -e SENTINEL_SENTINEL_REGISTRATION_TOKEN=your-token \
  sentinel-agent
```

### Kubernetes (Helm)

**Prerequisites:** Docker image built, `kubectl` configured, Helm 3 installed.

```bash
# Load image into kind (local clusters)
kind load docker-image sentinel-agent:latest

# Install the chart
helm install sentinel-agent ./charts/sentinel-agent

# Override values
helm install sentinel-agent ./charts/sentinel-agent \
  --set sentinel.apiUrl=https://your-sentinel.example.com \
  --set sentinel.registrationToken=your-token \
  --set sentinel.mockMode=false

# Upgrade
helm upgrade sentinel-agent ./charts/sentinel-agent

# Uninstall
helm uninstall sentinel-agent
```

### RBAC

A read-only ServiceAccount with permissions limited to:

| Resource | Verbs |
|----------|-------|
| pods | get, list, watch |
| events | get, list, watch |
| namespaces | get, list, watch |
| nodes | get, list, watch |
| deployments | get, list, watch |
| replicasets | get, list, watch |

No write permissions are granted. This follows the principle of least privilege.

### Health Checks

The agent uses exec-based liveness and readiness probes &mdash; no HTTP server is required.

- **Liveness probe**: Runs `cli_health()` every 15s. Exits 0 when the startup marker file exists.
- **Readiness probe**: Runs `cli_ready()` every 10s. Exits 0 when startup has completed.

### Created Resources

When deployed, Helm creates:

| Resource | Name | Purpose |
|----------|------|---------|
| `Deployment` | `sentinel-agent` | Single-replica pod |
| `ServiceAccount` | `sentinel-agent` | Pod identity |
| `Role` | `sentinel-agent-role` | Read-only Kubernetes permissions |
| `RoleBinding` | `sentinel-agent-rolebinding` | Binds role to service account |
| `ConfigMap` | `sentinel-agent-config` | Environment variable configuration |
| `Secret` | `sentinel-agent-secret` | Registration token (base64) |

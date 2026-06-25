# Sentinel Agent

A Kubernetes runtime security agent that detects pod failures, collects context evidence, runs diagnostics, and delivers structured reports to the SentinelAI control plane.

Supports real and mock mode — runs fully offline for development and CI, or against a live control plane for production.

## Current Phase

**Milestone 5 complete — Transport pipeline validated end-to-end**

The agent detects pod failures (CrashLoopBackOff, OOMKilled, ImagePullBackOff), collects Kubernetes context (pod spec, events, namespace, deployment chain, node), runs rule-based diagnostic analysis, and delivers structured reports to SentinelAI over HTTP. A retry loop with configurable limits handles transient delivery failures.

| Capability | Status | Notes |
|-----------|--------|-------|
| Detection (Watch API + polling) | ✅ | CrashLoopBackOff, OOMKilled, ImagePullBackOff |
| Context collection (6 collectors) | ✅ | Pod, Deployment, ReplicaSet, Namespace, Events, Node |
| Diagnostic analysis (rule-based) | ✅ | Per-incident-type analyzers with confidence scoring |
| Transport (HTTP delivery) | ✅ | Retries, mock mode, status tracking |
| Heartbeat (scheduler exists) | ⚠️ | Mock mode only — see [docs/required-updates.md](docs/required-updates.md) |
| Agent registration | ✅ | Real and mock flows |
| Persistent storage (SQLite) | ✅ | Alembic migrations for schema management |
| Helm deployment | ✅ | RBAC, ConfigMap, health probes |
| E2E validation (two-kind cluster) | ✅ | Cross-cluster NodePort delivery confirmed |

### Known Gaps

| Issue | Impact | Target |
|-------|--------|--------|
| Heartbeats in mock mode only | Control plane has no agent liveness visibility | See [required-updates.md](docs/required-updates.md) |
| SQLite in ephemeral pod | PENDING reports lost on pod restart | PVC or external queue |
| No idempotency key | Duplicate delivery possible on retry | sentinel-api dedup |
| No dead-letter queue | FAILED reports vanish after max_retries | DLQ table or alert |

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
│   ├── detection/               # Detection engine (Milestone 2)
│   │   ├── __init__.py
│   │   ├── incident.py          # SQLAlchemy Incident model + enums
│   │   ├── models.py            # Pydantic IncidentCandidate / IncidentResponse
│   │   ├── repositories.py      # IncidentRepository
│   │   ├── service.py           # DetectionService orchestrator
│   │   ├── watcher.py           # Kubernetes Watch API engine
│   │   ├── polling.py           # Periodic polling fallback
│   │   └── detectors/
│   │       ├── __init__.py
│   │       ├── base.py          # Detector ABC + DetectorRegistry
│   │       ├── crashloop.py     # CrashLoopBackOffDetector
│   │       ├── oomkilled.py     # OOMKilledDetector
│   │       └── imagepull.py     # ImagePullBackOffDetector
│   ├── collection/              # Context collection engine (Milestone 3)
│   │   ├── __init__.py
│   │   ├── models.py            # IncidentContext SQLAlchemy model + ContextType
│   │   ├── repositories.py      # IncidentContextRepository
│   │   ├── service.py           # CollectionService orchestrator
│   │   └── collectors/
│   │       ├── __init__.py
│   │       ├── base.py          # Collector ABC + ContextResult
│   │       ├── pod.py           # Pod metadata collector
│   │       ├── deployment.py    # Deployment collector (ownerRef tracing)
│   │       ├── replicaset.py    # ReplicaSet collector (ownerRef tracing)
│   │       ├── namespace.py     # Namespace metadata collector
│   │       ├── events.py        # Events collector (newest-first, capped)
│   │       └── node.py          # Node collector (if pod scheduled)
│   ├── diagnostics/             # Diagnostics engine (Milestone 4)
│   │   ├── __init__.py
│   │   ├── models.py            # DiagnosticReport model + DiagnosticResult
│   │   ├── repositories.py      # DiagnosticReportRepository
│   │   ├── service.py           # DiagnosticService orchestrator
│   │   └── analyzers/
│   │       ├── __init__.py
│   │       ├── base.py          # DiagnosticAnalyzer ABC
│   │       ├── image_pull.py    # ImagePullBackOff analyzer
│   │       ├── crashloop.py     # CrashLoopBackOff analyzer
│   │       └── oomkilled.py     # OOMKilled analyzer
│   ├── transport/               # Outbound delivery to SentinelAI (Milestone 5)
│   │   ├── __init__.py
│   │   ├── models.py            # OutboundReport model + OutboundStatus enum
│   │   ├── repositories.py      # OutboundReportRepository
│   │   ├── client.py            # SentinelAIClient (httpx)
│   │   ├── service.py           # TransportService (enqueue / deliver)
│   │   └── retry.py             # RetryService (background delivery loop)
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
│       ├── 0001_add_connectivity_tables.py
│       ├── 0002_add_incident_table.py
│       ├── 0003_add_incident_context_table.py
│       ├── 0004_add_diagnostic_report_table.py
│       └── 0005_add_outbound_report_table.py
├── alembic.ini
├── tests/
│   ├── test_settings.py
│   ├── test_bootstrap.py
│   ├── test_storage.py
│   ├── test_alembic.py
│   ├── test_detection_models.py
│   ├── test_detection_repository.py
│   ├── test_detectors.py
│   ├── test_detection_service.py
│   ├── test_collection_models.py
│   ├── test_collection_repository.py
│   ├── test_collection_collectors.py
│   ├── test_collection_service.py
│   ├── test_collection_integration.py
│   ├── test_diagnostics_models.py
│   ├── test_diagnostics_repository.py
│   ├── test_diagnostics_analyzers.py
│   ├── test_diagnostics_service.py
│   ├── test_transport_models.py
│   ├── test_transport_repository.py
│   ├── test_transport_client.py
│   ├── test_transport_service.py
│   └── test_transport_retry.py
├── charts/
│   └── sentinel-agent/          # Helm chart for Kubernetes deployment
├── docs/
│   └── required-updates.md      # Known gaps and pending changes
├── pyproject.toml
├── poetry.lock
├── Dockerfile
├── .gitignore
└── README.md
```

## Configuration

Settings are organized into seven nested Pydantic models and loaded from environment variables prefixed with `SENTINEL_`. There is no file-based loader.

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
settings.detection.enabled
settings.detection.polling_interval_seconds
settings.collection.enabled
settings.collection.max_events
settings.transport.enabled
settings.transport.base_url
settings.transport.timeout_seconds
settings.transport.max_retries
settings.transport.retry_interval_seconds
settings.transport.mock_mode
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
| `database_url` | `str` | `"sqlite:////data/sentinel_agent.db"` | non-empty |

**`DetectionConfig`** — detection engine settings.

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `enabled` | `bool` | `true` | — |
| `polling_interval_seconds` | `int` | `60` | `> 0` |

**`CollectionConfig`** — context collection settings for incident evidence gathering.

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `enabled` | `bool` | `true` | — |
| `max_events` | `int` | `20` | `>= 1` |

**`TransportConfig`** — outbound delivery settings for sending reports to SentinelAI.

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `enabled` | `bool` | `true` | — |
| `base_url` | `str` | `"https://api.sentinel.example.com"` | non-empty |
| `api_key` | `str` | `""` | — |
| `timeout_seconds` | `int` | `10` | `> 0` |
| `max_retries` | `int` | `5` | `>= 0` |
| `retry_interval_seconds` | `int` | `30` | `> 0` |
| `mock_mode` | `bool` | `true` | — |

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
| `SENTINEL_STORAGE_DATABASE_URL` | `settings.storage.database_url` | `sqlite:////data/sentinel_agent.db` |
| `SENTINEL_DETECTION_ENABLED` | `settings.detection.enabled` | `true` |
| `SENTINEL_DETECTION_POLLING_INTERVAL_SECONDS` | `settings.detection.polling_interval_seconds` | `60` |
| `SENTINEL_COLLECTION_ENABLED` | `settings.collection.enabled` | `true` |
| `SENTINEL_COLLECTION_MAX_EVENTS` | `settings.collection.max_events` | `20` |
| `SENTINEL_TRANSPORT_ENABLED` | `settings.transport.enabled` | `true` |
| `SENTINEL_TRANSPORT_BASE_URL` | `settings.transport.base_url` | `https://api.sentinel.example.com` |
| `SENTINEL_TRANSPORT_API_KEY` | `settings.transport.api_key` | `""` |
| `SENTINEL_TRANSPORT_TIMEOUT_SECONDS` | `settings.transport.timeout_seconds` | `10` |
| `SENTINEL_TRANSPORT_MAX_RETRIES` | `settings.transport.max_retries` | `5` |
| `SENTINEL_TRANSPORT_RETRY_INTERVAL_SECONDS` | `settings.transport.retry_interval_seconds` | `30` |
| `SENTINEL_TRANSPORT_MOCK_MODE` | `settings.transport.mock_mode` | `true` |

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

The agent uses SQLAlchemy with Alembic for schema management. Seven tables are defined by migrations `0001` through `0005`:

| Table | Purpose |
| --- | --- |
| `cluster_identity` | One row per registered cluster, tracks registration metadata and last-seen timestamp |
| `credentials` | API keys issued by the control plane, with optional expiry |
| `heartbeat_record` | Audit log of every heartbeat sent |
| `incident` | Detected failure conditions — id, type, severity, namespace, resource, status |
| `incident_context` | Collected context evidence linked to an incident — pod spec, events, namespace metadata, etc. |
| `diagnostic_report` | Diagnostic analysis results — root cause, confidence score, evidence, analyzer metadata |
| `outbound_report` | Delivery tracking for reports sent to SentinelAI — status, retry count, payload |

### `DatabaseManager`

`DatabaseManager` is the only way the rest of the application should talk to SQLAlchemy. It is constructed with a database URL and must be `initialize()`d before use. After initialization it exposes:

- `db.engine` — a SQLAlchemy `Engine`
- `db.session_factory` — a `sessionmaker[Session]`
- `db.session()` — a context-managed `Session` that commits on success, rolls back on exception, and always closes

```python
from agent.storage.database import DatabaseManager

db = DatabaseManager("sqlite:////data/sentinel_agent.db")
db.initialize()

with db.session() as session:
    # use session ...
    ...
```

### Repositories

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

## Runtime Startup Sequence

The `RuntimeManager` orchestrates the full agent lifecycle from `src/main.py`. The startup sequence is:

```
bootstrap → DB init → K8s client → registration → credentials → heartbeat → detection → transport retry
```

1. **Bootstrap** — configure structlog JSON logging, emit startup event with agent identity
2. **Database** — initialize SQLAlchemy engine, create tables via `Base.metadata.create_all()`
3. **Kubernetes client** — connect to the Kubernetes API for cluster metadata (graceful if unavailable)
4. **Registration** — register with SentinelAI control plane via `RegistrationService.register()`
5. **Credentials** — persist API key and agent ID returned by registration
6. **Heartbeat** — start `HeartbeatScheduler` on a background thread (every `interval_seconds`)
7. **Detection** — start `DetectionService` (pod watcher + poller + detector chain)
8. **Transport retry** — start `RetryService` background loop (delivers pending reports every `retry_interval_seconds`)

If registration fails (or is in mock mode), detection and transport retry still start — the agent runs independently but without a control plane connection.

```python
from agent.runtime.runtime_manager import RuntimeManager
from agent.config.settings import get_settings

manager = RuntimeManager(get_settings())
manager.start()
manager.wait()    # blocks until SIGTERM/SIGINT
manager.stop()
```

### Health Checks

The agent writes a timestamp marker to `/tmp/sentinel-agent-ready` at the end of a successful startup. Kubernetes exec probes check this file:

- **Liveness probe**: checks marker file exists every 15s
- **Readiness probe**: checks `RuntimeManager.started` flag every 10s

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

db = DatabaseManager("sqlite:////data/sentinel_agent.db")
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
  │ .send(payload)    │  (mock: logs and returns)
  └──────────────────┘
```

The `HeartbeatScheduler` wraps an APScheduler `BackgroundScheduler`. On `start()` it schedules a recurring job at `settings.heartbeat.interval_seconds`. Each tick:

1. Builds a `HeartbeatPayload` with the current `cluster_id`, `agent_version`, and status.
2. Sends it via `HeartbeatClient.send()`.
3. In mock mode (default), the tick is logged but **no HTTP call is made**.

**Known gap**: To enable real heartbeats, the sentinel-api needs a `POST /agent/heartbeat` endpoint and the agent's `sentinel.mockMode` must be `false`. See [docs/required-updates.md](docs/required-updates.md) for the full change list.

## Mock Mode

When `SENTINEL_SENTINEL_MOCK_MODE=true` (the default), the agent operates without a live Sentinel control plane:

- **Registration** — `RegistrationClient.register()` returns a synthetic `RegistrationResponse` with a `mock-agent-*` agent ID and `mock-api-key-*` key. The full registration flow (metadata collection, payload assembly, local persistence) still executes.
- **Heartbeat** — `HeartbeatClient.send()` logs the payload and returns `True`. `HeartbeatScheduler._tick()` logs the tick and returns without making an HTTP call.
- **Transport** — `SentinelAIClient.deliver()` logs the payload and returns `{"accepted": True}`. The full enqueue → deliver → DELIVERED lifecycle executes locally.

Set `SENTINEL_SENTINEL_MOCK_MODE=false` and `SENTINEL_TRANSPORT_MOCK_MODE=false` to connect to a real control plane.

## Detection Architecture

The detection engine observes Kubernetes pods and creates incidents when known failure conditions occur. It runs in the background after registration and heartbeat startup.

```
        ┌─────────────────────────┐
        │    DetectionService      │
        │  .start()                │
        └──────┬─────────┬────────┘
               │         │
         ┌─────▼──┐  ┌──▼──────┐
         │Watcher │  │  Poller │  (fallback)
         │(Watch  │  │  every  │
         │  API)  │  │  60s    │
         └───┬────┘  └──┬──────┘
             │          │
             ▼          ▼
       ┌────────────────────┐
       │  DetectorRegistry   │
       │  .detect_all(pod)   │
       └──┬─────┬──────┬────┘
          │     │      │
     ┌────▼┐ ┌──▼──┐ ┌─▼──────┐
     │Crash│ │ OOM │ │ Image  │
     │Loop │ │Kill │ │Pull    │
     └──┬──┘ └──┬──┘ └──┬─────┘
        │      │      │
        ▼      ▼      ▼
   ┌──────────────────────┐
   │  IncidentRepository   │
   │  (create / update)    │
   └──────────┬───────────┘
              │  (on new incident only)
              ▼
   ┌──────────────────────┐
   │  CollectionService   │
   │  (collect context)   │
   └──────────┬───────────┘
              │  (on new incident only)
              ▼
   ┌──────────────────────┐
   │  DiagnosticService   │
   │  (analyze & persist) │
   └──────────┬───────────┘
              │  (on new incident only)
              ▼
   ┌──────────────────────┐
   │  TransportService    │
   │  (enqueue delivery)  │
   └──────────────────────┘
```

### Incident Types

| Detector | Condition | Severity |
|----------|-----------|----------|
| `CrashLoopBackOffDetector` | `containerStatuses[*].state.waiting.reason == "CrashLoopBackOff"` | CRITICAL |
| `OOMKilledDetector` | `containerStatuses[*].lastState.terminated.reason == "OOMKilled"` | HIGH |
| `ImagePullBackOffDetector` | `containerStatuses[*].state.waiting.reason == "ImagePullBackOff"` | HIGH |

### Incident Lifecycle

1. **Detection** — A detector returns an `IncidentCandidate` for a failing pod.
2. **Deduplication** — If an OPEN incident exists for the same `(incident_type, namespace, resource_name)`, its `last_seen_at` is updated instead of creating a new record.
3. **Context Collection** — On new incident creation, `CollectionService` collects Pod, Deployment, ReplicaSet, Namespace, Events, and Node context and persists it to the `incident_context` table.
4. **Diagnostic Analysis** — `DiagnosticService` matches the incident type to an analyzer, runs analysis against the collected context, and persists a `DiagnosticReport`. If no analyzer matches, a fallback report is created.
5. **Transport Enqueue** — `TransportService` enqueues the incident + diagnostic report for delivery (always, even on fallback reports).
6. **Resolution** — When a previously-failing pod becomes healthy (all containers ready) or is deleted, all OPEN incidents for that namespace/name are marked RESOLVED.

### Components

- **`PodWatcher`** — Opens a Kubernetes Watch API stream on pods. Runs on a background thread with automatic reconnect and exponential backoff (1–60s). Calls `DetectionService._handle_event()` for each event.
- **`PodPoller`** — Fallback that lists all pods every `polling_interval_seconds`. Runs on a daemon thread. Invokes the same detector registry.
- **`Detector`** — Abstract base class. Each detector implements `detect(pod) -> IncidentCandidate | None`.
- **`DetectionService`** — Orchestrator that starts the watcher thread and poller, routes events through detectors, and persists/updates incidents via the repository.
- **`IncidentRepository`** — CRUD operations on the `incident` table. Supports `create`, `get_by_id`, `list_open`, `find_open_duplicate`, `mark_resolved`, `update_last_seen`, and `resolve_pod_incidents`.

### How to Verify

After deployment, create failing pods to trigger detection:

```bash
# ImagePullBackOff
kubectl run test-image-pull --image=does-not-exist -n demo-apps

# Check agent logs for detection events
kubectl logs -n sentinel -l app.kubernetes.io/name=sentinel-agent | grep incident_detected

# Check for transport delivery
kubectl logs -n sentinel -l app.kubernetes.io/name=sentinel-agent | grep report_delivered
```

### Configuration

| Environment Variable | Setting | Default |
|---------------------|---------|---------|
| `SENTINEL_DETECTION_ENABLED` | `settings.detection.enabled` | `true` |
| `SENTINEL_DETECTION_POLLING_INTERVAL_SECONDS` | `settings.detection.polling_interval_seconds` | `60` |

## Context Collection Architecture

The collection engine gathers Kubernetes context evidence for each incident at the moment it is created. It runs as part of `DetectionService._persist_or_update()` — when a new incident is created, collection fires automatically before the method returns.

```
        DetectionService
        _persist_or_update()
               │
               ▼  (new incident only)
        ┌──────────────┐
        │  Collection   │
        │  Service      │
        └──┬───┬───┬───┘
           │   │   │
     ┌─────▼┐ ┌▼──┐ ┌▼──────┐  ...  6 collectors total
     │ Pod  │ │NS │ │Events │
     │      │ │   │ │       │
     └──────┘ └───┘ └───────┘
           │   │   │
           ▼   ▼   ▼
     ┌──────────────────┐
     │IncidentContext   │
     │Repository        │
     │(persist to SQLite)│
     └──────────────────┘
```

### Context Types

| ContextType | Collector | Always Returns | Description |
|-------------|-----------|----------------|-------------|
| `POD` | `PodContextCollector` | Yes | Pod metadata, spec, status, ownerReferences |
| `DEPLOYMENT` | `DeploymentContextCollector` | No | Traces owner references: Pod → ReplicaSet → Deployment |
| `REPLICASET` | `ReplicaSetContextCollector` | No | Traces owner reference from Pod |
| `NAMESPACE` | `NamespaceContextCollector` | Yes | Namespace metadata (labels, annotations, UID) |
| `EVENTS` | `EventsContextCollector` | No | Recent Kubernetes events for the pod, newest-first, capped at `max_events` |
| `NODE` | `NodeContextCollector` | No | Node metadata and status (only if pod is scheduled to a node) |

### Collector Responsibilities

- **`PodContextCollector`** — Extracts the pod object's metadata (name, namespace, UID, labels, annotations), spec (containers, volumes, node selector), status (phase, conditions, container statuses), and owner references. Always returns a result.

- **`DeploymentContextCollector`** — Follows the pod's `ownerReferences` chain to find the owning ReplicaSet, then the ReplicaSet's `ownerReferences` to find the Deployment. Fetches the Deployment via the Kubernetes API. Returns `None` if the pod is not part of a Deployment (e.g., a standalone pod).

- **`ReplicaSetContextCollector`** — Looks up the pod's first `ownerReferences` entry with `kind: ReplicaSet` and fetches it from the Kubernetes API. Returns `None` if no ReplicaSet owner exists.

- **`NamespaceContextCollector`** — Fetches the namespace object for the pod's namespace via `CoreV1Api.read_namespace()`. Always returns result with name, UID, labels, and annotations.

- **`EventsContextCollector`** — Lists all events in the namespace via `CoreV1Api.list_namespaced_events()`, filters to those matching the pod name, sorts by `last_timestamp` descending, and caps at `settings.collection.max_events` (default 20). Returns `None` if no events match.

- **`NodeContextCollector`** — Reads `pod.spec.node_name` and fetches the node object via `CoreV1Api.read_node()`. Returns `None` if the pod hasn't been scheduled to a node yet.

### Context Package

Callers receive an `IncidentContextPackage` dataclass containing all collected context:

```python
@dataclass
class IncidentContextPackage:
    incident: Incident
    pod: dict | None = None
    deployment: dict | None = None
    replicaset: dict | None = None
    namespace: dict | None = None
    events: dict | None = None
    node: dict | None = None
```

Fields are `None` for collectors that returned `None` (optional context) or raised an error.

### Resilience

- **Per-collector isolation** — If a collector raises an exception, it is logged and the error is attributed only to that collector. All other collectors continue normally.
- **No pod, no collection** — When `collect_for_incident()` is called without a pod dict (e.g., from the poller path that doesn't hold the full pod object), collection is skipped entirely.
- **Collection failures don't crash detection** — The `try/except` in `DetectionService._persist_or_update()` catches collection errors so they never propagate to the watcher or poller loop.
- **Only on new incidents** — Collection fires only when a new `Incident` record is created. Duplicate updates (same incident seen again) skip collection entirely.

### Storage

Collected context is persisted in the `incident_context` table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID` (PK) | Auto-generated |
| `incident_id` | `FK → incident.id` | Parent incident |
| `context_type` | `Enum(ContextType)` | `POD`, `DEPLOYMENT`, `REPLICASET`, `NAMESPACE`, `EVENTS`, `NODE` |
| `context_payload` | `JSON` | Collector-specific payload |
| `collected_at` | `DateTime` | Server-generated timestamp |

Each incident can have multiple context rows (one per collected type).

## Diagnostics Architecture

The diagnostics engine converts incidents + collected context into structured diagnostic reports. It runs automatically after context collection completes for every newly created incident.

```
        DetectionService
        _persist_or_update()
               │
               ▼  (new incident only)
        ┌──────────────┐
        │  Collection   │
        │  Service      │
        └──┬───┬───┬───┘
           │   │   │
     ┌─────▼┐ ┌▼──┐ ┌▼──────┐
     │ Pod  │ │NS │ │Events │  6 collectors total
     └──────┘ └───┘ └───────┘
           │   │   │
           ▼   ▼   ▼
     ┌──────────────────────┐
     │  DiagnosticService   │
     │  .analyze_incident() │
     └──────────┬───────────┘
                │
                ▼
     ┌──────────────────────┐
     │  Analyzer Selection   │
     │  (by incident_type)   │
     └──┬──────┬──────┬─────┘
        │      │      │
   ┌────▼──┐ ┌─▼───┐ ┌▼────────┐
   │Image  │ │Crash│ │OOMKilled│
   │Pull   │ │Loop │ │         │
   └───┬───┘ └──┬──┘ └────┬────┘
       │        │         │
       ▼        ▼         ▼
   ┌──────────────────────────┐
   │  DiagnosticReport        │
   │  (persisted to SQLite)   │
   └──────────────┬───────────┘
                  │
                  ▼
   ┌──────────────────────────┐
   │  TransportService        │
   │  .enqueue(incident,      │
   │    diagnostic_report)    │
   └──────────────┬───────────┘
                  │
                  ▼
   ┌──────────────────────────┐
   │  SentinelAIClient        │
   │  POST /incident          │
   │  (mock: no-op)           │
   └──────────────────────────┘
```

### Supported Root Causes

| Analyzer | Root Cause | Confidence | Signals |
|----------|------------|------------|---------|
| `ImagePullAnalyzer` | Container image does not exist | 0.97 | `ImagePullBackOff` + `"not found"` message |
| `ImagePullAnalyzer` | Container registry authentication failure | 0.92 | `"unauthorized"`, `"authentication required"` |
| `ImagePullAnalyzer` | Container registry unavailable | 0.85 | `"timeout"`, `"connection refused"`, `"no such host"` |
| `ImagePullAnalyzer` | Image pull failed — unknown cause | 0.60 | Fallback (no specific signal matched) |
| `CrashLoopAnalyzer` | Application repeatedly crashing during startup | 0.90 | Restart count > 3, `CrashLoopBackOff` waiting reason |
| `CrashLoopAnalyzer` | Application configuration error | 0.80 | `"configuration"`, `"missing environment variable"` |
| `CrashLoopAnalyzer` | Container repeatedly crashing — cause unknown | 0.60 | Fallback |
| `OOMKilledAnalyzer` | Container exceeded memory limit | 0.98 | `OOMKilled` terminated reason, event reason |
| `OOMKilledAnalyzer` | Container exceeded memory limit | 0.90 | Ambiguous signals (events only, no direct OOM) |

### Analyzer Interface

Each analyzer implements the `DiagnosticAnalyzer` abstract base class:

```python
class DiagnosticAnalyzer(ABC):
    @abstractmethod
    def analyze(
        self, incident: Incident, context_package: IncidentContextPackage
    ) -> DiagnosticResult | None: ...
```

- Returns `DiagnosticResult` with `root_cause`, `confidence`, `summary`, `evidence`, `analyzer_name`
- Returns `None` if the incident type does not match this analyzer
- All analysis is deterministic and rule-based

### DiagnosticService

`DiagnosticService` orchestrates the analysis:

1. **Load incident** — looks up the incident by ID via `IncidentRepository`
2. **Select analyzer** — matches `incident_type` to an analyzer class via registry
3. **Load context** — reads stored context from `incident_context` table via `IncidentContextRepository`
4. **Run analyzer** — calls `analyzer.analyze(incident, context_package)`
5. **Fallback** — if analyzer returns `None`, creates a fallback `DiagnosticReport` with root cause "Unknown (no diagnostic analysis)"
6. **Persist report** — stores the `DiagnosticReport` in the `diagnostic_report` table
7. **Transport** — enqueues the report for delivery (always, even for fallback reports)

### DiagnosticReport Model

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID` (PK) | Auto-generated |
| `incident_id` | `FK → incident.id` | Parent incident |
| `root_cause` | `Text` | Human-readable root cause description |
| `confidence` | `Float` | Confidence score (0.0–1.0) |
| `summary` | `Text` (nullable) | Optional summary |
| `evidence` | `JSON` (nullable) | Signals used, context sources, container statuses |
| `analyzer_name` | `String(128)` | Name of the analyzer that produced the report |
| `created_at` | `DateTime` | Server-generated timestamp |

### How to Verify

Create failing pods and check diagnostic reports:

```bash
# ImagePullBackOff
kubectl run test-diag --image=does-not-exist -n demo-apps

# Check agent logs for diagnostic completion
kubectl logs -n sentinel -l app.kubernetes.io/name=sentinel-agent | grep diagnostic_completed

# Expected output (JSON):
# {"event": "diagnostic_completed", "incident_id": "...", "incident_type": "ImagePullBackOff",
#  "root_cause": "Container image does not exist", "confidence": 0.97}
```

## Transport Architecture

The transport layer delivers diagnostic reports from the agent to the SentinelAI control plane.
It runs automatically after diagnostics completes for each newly created incident.

```
Diagnostics complete
        │
        ▼
┌───────────────────┐     ┌──────────────────────┐
│  TransportService  │────▶│  OutboundReport       │
│  .enqueue()        │     │  (status=PENDING)     │
└────────┬──────────┘     └──────────┬───────────┘
         │                           │
         │  deliver_pending()        │  (background thread)
         ▼                           ▼
┌───────────────────┐     ┌──────────────────────┐
│  SentinelAIClient  │     │  RetryService         │
│  POST /incident    │     │  (every interval_sec) │
└────────┬──────────┘     └──────────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 DELIVERED  FAILED
 (success)  (after max_retries)
```

### Components

- **`OutboundReport`** — SQLAlchemy model tracking delivery of one (incident, diagnostic) pair. Starts `PENDING`, transitions to `DELIVERED` on success or `FAILED` after exhausting retries.

- **`OutboundReportRepository`** — CRUD for `outbound_report` table. Supports `create()`, `get_pending()` (ordered FIFO, default limit 50), `mark_delivered()`, `increment_retry()`, and `mark_failed()`.

- **`SentinelAIClient`** — HTTP(S) client using `httpx`. POSTs a flat payload matching the sentinel-api `Incident` model to `{base_url}/incident`. Skips Authorization header when `api_key` is empty. In mock mode, logs the payload and returns `{"accepted": True}` without making an HTTP call.

- **`TransportService`** — Orchestrator with two public methods:
  - `enqueue(incident, diagnostic_report)` — builds flat JSON payload, creates `PENDING` OutboundReport
  - `deliver_pending(limit=50)` — iterates pending reports, attempts delivery, updates status

- **`RetryService`** — Background daemon thread that calls `deliver_pending()` at a configurable interval. Survives individual exceptions. Uses `threading.Event` for clean shutdown.

### Delivery Flow

1. **Enqueue** — `TransportService.enqueue()` serializes incident + diagnostic data into a flat JSON payload matching the sentinel-api `Incident` model and creates an `OutboundReport` with `status=PENDING`.
2. **Delivery attempt** — `deliver_pending()` reads pending reports (oldest first), deserializes each payload, and calls `SentinelAIClient.deliver()`.
3. **Outcome** — On HTTP 2xx, the report is marked `DELIVERED` with a timestamp. On failure, `retry_count` is incremented. If `retry_count >= max_retries`, the report is marked `FAILED`.
4. **Background retry** — `RetryService` runs `deliver_pending()` every `retry_interval_seconds` on a background daemon thread, picking up any remaining `PENDING` reports.

### Payload Structure

The payload is a flat dict matching the sentinel-api `Incident` model (Pydantic v2 — extra fields rejected):

```json
{
  "service": "test-crash-pod",
  "severity": "CRITICAL",
  "event_type": "crashloopbackoff",
  "namespace": "demo-apps",
  "message": "Container crash-looping: back-off 5m0s restarting",
  "timestamp": "2026-06-25T12:34:56.789012+00:00"
}
```

### OutboundReport Model

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID` (PK) | Auto-generated |
| `incident_id` | `FK → incident.id` | Parent incident (indexed) |
| `diagnostic_report_id` | `FK → diagnostic_report.id` | Source diagnostic (indexed) |
| `payload` | `Text` | Full JSON payload for delivery |
| `status` | `String(16)` | `PENDING`, `DELIVERED`, or `FAILED` (indexed) |
| `retry_count` | `Integer` | Number of delivery attempts so far |
| `last_attempt_at` | `DateTime` (nullable) | When the last delivery was attempted |
| `delivered_at` | `DateTime` (nullable) | When delivery succeeded |
| `created_at` | `DateTime` | When the report was enqueued |

### Configuration

| Environment Variable | Setting | Default |
|---------------------|---------|---------|
| `SENTINEL_TRANSPORT_ENABLED` | `settings.transport.enabled` | `true` |
| `SENTINEL_TRANSPORT_BASE_URL` | `settings.transport.base_url` | `https://api.sentinel.example.com` |
| `SENTINEL_TRANSPORT_API_KEY` | `settings.transport.api_key` | `""` |
| `SENTINEL_TRANSPORT_TIMEOUT_SECONDS` | `settings.transport.timeout_seconds` | `10` |
| `SENTINEL_TRANSPORT_MAX_RETRIES` | `settings.transport.max_retries` | `5` |
| `SENTINEL_TRANSPORT_RETRY_INTERVAL_SECONDS` | `settings.transport.retry_interval_seconds` | `30` |
| `SENTINEL_TRANSPORT_MOCK_MODE` | `settings.transport.mock_mode` | `true` |

## End-to-End Testing

The transport pipeline has been validated end-to-end using two kind clusters on the same Docker network.

### Topology

```
┌──────────────────────────────────────────────────────────┐
│  Docker kind network (172.18.0.0/16)                     │
│                                                          │
│  ┌─ sentinel cluster (port 43513) ─┐  ┌─ target cluster │
│  │                                    │  (port 43091)   │
│  │ sentinel-api     NodePort 30586 ──── sentinel-agent  │
│  │ RabbitMQ                          │  test-detection  │
│  │ incident worker                   │  pods            │
│  └────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────┘
```

Both clusters are created on the same Docker network (`kind`). The sentinel-api is exposed via NodePort 30586 on the control-plane node (172.18.0.3). The agent pod in the target cluster reaches it at `http://172.18.0.3:30586`.

### Setup

```bash
# Create sentinel cluster (API, RabbitMQ, workers)
kind create cluster --name sentinel --config ~/SentinelAI-v1/kind-config.yaml
kubectl apply -f ~/SentinelAI-v1/k8s/namespace.yaml
kubectl apply -f ~/SentinelAI-v1/k8s/

# Create target cluster (agent + test pods)
kind create cluster --name target --config ~/Sentinel-Agent/kind-config.yaml
kubectl apply -f ~/Sentinel-Agent/k8s/namespace.yaml
kubectl apply -f ~/Sentinel-Agent/k8s/

# Build and load sentinel-api image
docker build -t sentinel-api:latest ~/SentinelAI-v1
kind load docker-image sentinel-api:latest --name sentinel
kubectl rollout restart deployment -n sentinel

# Build and load sentinel-agent image
docker build -t sentinel-agent:latest ~/Sentinel-Agent
kind load docker-image sentinel-agent:latest --name target
kubectl rollout restart deployment -n sentinel-agent
```

### Verification

Create a failing pod in the target cluster to trigger the full pipeline:

```bash
kubectl run test-e2e --image=does-not-exist -n demo-apps

# Watch the agent detect, collect, diagnose, and deliver
kubectl logs -n sentinel-agent -l app.kubernetes.io/name=sentinel-agent

# Expected events in order:
# 1. incident_detected — detector finds the failure
# 2. context_collected — evidence gathered
# 3. diagnostic_completed — root cause identified
# 4. report_enqueued — transport creates PENDING record
# 5. report_delivered — HTTP POST to sentinel-api returns 200

# On the sentinel side, check the incident worker consumed it:
kubectl logs -n sentinel -l app.kubernetes.io/name=sentinel-worker
# Expected: "Received incident" with the pod details
```

### Cross-Cluster Networking

Kind clusters share a Docker bridge network. The sentinel-api control-plane node is reachable from the target cluster at `172.18.0.3:30586`.

- **sentinel-api node IP**: `172.18.0.3` (check with `kubectl get nodes -o wide -n sentinel`)
- **NodePort**: `30586` (configured in sentinel-api service)
- **Transport URL** in `values.yaml`: `http://172.18.0.3:30586`

If IPs differ (Docker bridge assignment varies), re-check and update `charts/sentinel-agent/values.yaml`:

```bash
kubectl get nodes -o wide -n sentinel  # get INTERNAL-IP
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
  --set sentinel.apiUrl=http://172.18.0.3:30586 \
  --set sentinel.mockMode=false \
  --set sentinel.registrationToken=your-token

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

The agent uses exec-based liveness and readiness probes — no HTTP server is required.

- **Liveness probe**: checks `/tmp/sentinel-agent-ready` marker file every 15s
- **Readiness probe**: checks `RuntimeManager.started` flag every 10s

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

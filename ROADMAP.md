# Sentinel Agent — Production Readiness Roadmap

**Verdict:** Not production-grade. Deploying as-is risks data loss, silent failures, and zero observability.

~13 days of work across 7 phases to go from prototype → production-grade. Phase 1 is a hard prerequisite before any real deployment.

---

## Phase 1 — Zero-Day Reliability (2 days)

| Priority | Area | What | Why |
|----------|------|------|-----|
| P0 | Storage | Swap SQLite for PostgreSQL with connection pooling (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`). Keep SQLite as dev-only fallback via env override. | SQLite corrupts under concurrent writes from watcher + poller + heartbeat threads. |
| P0 | Schema | Run Alembic migrations at startup instead of `Base.metadata.create_all()`. Keep `create_all` as fresh-DB fallback. | `create_all` does not apply missing columns/tables from later migrations. Existing DBs silently stay stale. |
| P0 | Health | Check DB connectivity (`SELECT 1`), K8s API availability, and watchdog thread liveness. Return detailed JSON. | Current probes only check a file marker — false-positive health hides real outages. |

## Phase 2 — Storage & Data Safety (2 days)

| Area | What |
|------|------|
| PVC | Add PersistentVolumeClaim (default 10Gi `ReadWriteOnce`). Keep emptyDir as dev opt-in. |
| preStop | Add `preStop` lifecycle hook for graceful DB flush. `terminationGracePeriodSeconds: 30`. |
| Retry | Wrap registration HTTP call with 3 retries, exponential backoff (1s, 2s, 4s). |
| Jitter | Add `random.uniform()` to watcher reconnect backoff — prevents thundering herd on K8s API recovery. |
| Pooling | Expose pool class/size in `StorageConfig`. `NullPool` for SQLite, `QueuePool(5,10)` for PostgreSQL. |

## Phase 3 — Observability (3 days)

| Area | What |
|------|------|
| Metrics | Prometheus `/metrics` endpoint on `:9090`. Counters for incidents, collection, heartbeats, registration. Histogram for detection latency. Pool stats. |
| Errors | Structured error hierarchy (`SentinelError` → `RegistrationError`, `CollectionError`, `DatabaseError`, `DetectionError`). Each carries `error_code` string for alerting. |
| Health | Dedicated HTTP server on `:8080` with `/health` and `/ready` endpoints returning component-level JSON. |

## Phase 4 — Resilience & Operations (2 days)

| Area | What |
|------|------|
| Circuit breaker | Sliding-window circuit breaker for K8s API calls. Open at >50% errors over 60s for 10s. |
| NetworkPolicy | Deny-all-egress by default. Allow only Sentinel API + K8s API server. |
| PDB | `minAvailable: 1` when `replicas > 1`. Configurable. |
| PriorityClass | Default `value: 1000000`. Configurable. |
| HPA | CPU-based autoscaling at 70% target. Opt-in via `.Values.autoscaling.enabled`. |

## Phase 5 — Security (1 day)

| Area | What |
|------|------|
| Credentials | Encrypt API key at rest using `cryptography.fernet` with cluster-derived key. |
| Container user | Match Dockerfile `USER` UID with Helm `securityContext.runAsUser`. |
| DB secrets | Move DB URL to Secret (not ConfigMap) when PostgreSQL is the target. |

## Phase 6 — Testing & CI/CD (2 days initial, ongoing)

| Area | What |
|------|------|
| Concurrency | Test 5 simultaneous threads writing + reading from DB. Verify no corruption. |
| Integration | Formalize kind-based e2e test as automated CI step. |
| Load test | Simulate 100 pod events per minute. Measure latency and memory growth. |
| CI pipeline | Lint → type-check → unit tests → integration → Docker build → Helm lint. Auto-versioning via git tags. Trivy scan on image. |

## Phase 7 — Polish (1 day)

| Area | What |
|------|------|
| Hot-reload | Add `Settings.reload()` via SIGHUP handler. |
| Testability | Make `KubernetesClient` accept injectable API stubs in constructor. |
| Helm | Auto-sync `Chart.yaml appVersion` from `pyproject.toml` in CI. |

---

## Effort Summary

| Phase | Days | Risk Reduced |
|-------|------|-------------|
| P1: Zero-Day Reliability | 2 | Data loss, health false-positives |
| P2: Storage & Safety | 2 | Data loss under restart/load |
| P3: Observability | 3 | Blind operation, no alerting |
| P4: Resilience & Ops | 2 | Outage under failure conditions |
| P5: Security | 1 | Credential exposure |
| P6: Testing & CI/CD | 2+ | Regressions, quality gate |
| P7: Polish | 1 | Developer experience |
| **Total** | **~13 days** | |

## Quick Wins (done in <30 min each)

- Add `check_same_thread=False` + WAL mode pragma to SQLite engine for dev stability
- Add `priorityClassName` to deployment template
- Match Dockerfile numeric UID with Helm securityContext
- Add `depends_on` marker to migration versions
- Set `terminationGracePeriodSeconds` to 30

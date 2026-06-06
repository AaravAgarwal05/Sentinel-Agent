# Sentinel Agent

A Kubernetes runtime security agent that performs detection, evidence collection, diagnostics, and remediation across a cluster.

## Current Phase

**Phase 0 — Runtime Foundation**

This phase ships a clean production-grade skeleton: a structured JSON logger, a pydantic-settings configuration model, a runtime bootstrap manager, and a working entry point. Every future module — registration, auth, heartbeat, detection, collection, diagnostics, transport, execution, storage, leader — is scaffolded as a package but contains no implementation. Those will land in subsequent phases.

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
│   │   └── settings.py          # pydantic-settings Settings
│   ├── registration/            # Phase N+
│   ├── auth/                    # Phase N+
│   ├── heartbeat/               # Phase N+
│   ├── detection/               # Phase N+
│   ├── collection/              # Phase N+
│   ├── diagnostics/             # Phase N+
│   ├── transport/               # Phase N+
│   ├── execution/               # Phase N+
│   ├── storage/                 # Phase N+
│   ├── leader/                  # Phase N+
│   └── runtime/
│       ├── __init__.py
│       └── bootstrap.py         # BootstrapManager
├── tests/
│   ├── test_settings.py
│   └── test_bootstrap.py
├── charts/
│   └── sentinel-agent/          # Helm chart (Phase N+)
├── pyproject.toml
├── poetry.lock
├── Dockerfile
├── .gitignore
└── README.md
```

## Configuration

Settings are loaded from environment variables (prefix `SENTINEL_`) or a `.env` file at the project root.

| Variable | Default | Description |
| --- | --- | --- |
| `SENTINEL_AGENT_NAME` | `sentinel-agent` | Agent identifier |
| `SENTINEL_AGENT_VERSION` | `0.1.0` | Agent version |
| `SENTINEL_ENVIRONMENT` | `development` | Runtime environment name |
| `SENTINEL_LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

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
  "log_level": "INFO"
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

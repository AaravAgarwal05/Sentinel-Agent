"""Lightweight exec-based health check for Kubernetes probes."""

from __future__ import annotations

import sys
from pathlib import Path

MARKER_PATH = Path("/tmp/sentinel-agent-ready")


def is_healthy() -> bool:
    """Return True if the startup marker file exists."""
    return MARKER_PATH.exists()


def is_ready() -> bool:
    """Return True if the startup marker file exists (startup completed)."""
    return MARKER_PATH.exists()


def cli_health() -> None:
    """CLI entry point for exec-based liveness probe. Exits 0 if healthy, 1 otherwise."""
    sys.exit(0 if is_healthy() else 1)


def cli_ready() -> None:
    """CLI entry point for exec-based readiness probe. Exits 0 if ready, 1 otherwise."""
    sys.exit(0 if is_ready() else 1)


if __name__ == "__main__":
    cli_health()

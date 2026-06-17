"""Sentinel Agent entry point."""

from __future__ import annotations

from agent.runtime.runtime_manager import RuntimeManager


def main() -> None:
    """Initialize and start the Sentinel Agent runtime."""
    mgr = RuntimeManager()
    mgr.start()


if __name__ == "__main__":
    main()

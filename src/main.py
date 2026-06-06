"""Sentinel Agent entry point."""

from __future__ import annotations

from agent.runtime.bootstrap import BootstrapManager


def main() -> None:
    """Initialize and start the Sentinel Agent runtime."""
    bootstrap = BootstrapManager()
    bootstrap.start()


if __name__ == "__main__":
    main()

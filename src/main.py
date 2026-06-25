"""Sentinel Agent entry point.

Starts the runtime, blocks until a termination signal (SIGTERM / SIGINT),
then performs a graceful shutdown.
"""

from __future__ import annotations

from agent.runtime.runtime_manager import RuntimeManager


def main() -> None:
    """Initialize and start the Sentinel Agent runtime.

    The call to ``wait()`` blocks the main thread indefinitely. Register
    signal handlers so that ``SIGTERM`` (Kubernetes pod termination) or
    ``SIGINT`` (Ctrl+C) trigger a graceful shutdown.
    """
    mgr = RuntimeManager()
    mgr.start()
    mgr.wait()
    mgr.stop()


if __name__ == "__main__":
    main()

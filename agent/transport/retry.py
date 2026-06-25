"""Periodic retry engine for failed outbound deliveries."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from agent.common.logging import get_logger

if TYPE_CHECKING:
    from agent.transport.service import TransportService

_logger = get_logger("agent.transport.retry")


class RetryService:
    """Periodically retries PENDING outbound reports.

    Runs on a background daemon thread at a configurable interval.
    Delegates delivery attempts to :class:`TransportService`.
    """

    def __init__(
        self,
        transport_service: TransportService,
        interval_seconds: int = 30,
    ) -> None:
        """Initialise the retry service.

        Args:
            transport_service: The transport service to delegate delivery to.
            interval_seconds: Seconds between retry cycles (default 30).
        """
        self._transport: TransportService = transport_service
        self._interval: int = interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()

    def start(self) -> None:
        """Start the background retry loop."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="transport-retry",
        )
        self._thread.start()
        _logger.info("retry_service_started", interval=self._interval)

    def stop(self) -> None:
        """Signal the retry loop to stop."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        _logger.info("retry_service_stopped")

    @property
    def running(self) -> bool:
        """Whether the retry loop is currently active."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        """Retry loop body."""
        while not self._stop_event.is_set():
            try:
                processed = self._transport.deliver_pending()
                if processed:
                    _logger.info("retry_cycle_completed", processed=processed)
            except Exception:
                _logger.exception("retry_cycle_failed")
            self._stop_event.wait(self._interval)

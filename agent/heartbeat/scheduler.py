"""APScheduler wrapper for periodic heartbeat transmission."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from agent.common.logging import get_logger
from agent.config.settings import get_settings
from agent.heartbeat.service import HeartbeatService

logger = get_logger(__name__)


class HeartbeatScheduler:
    """Manages a background scheduler that fires heartbeats on an interval.

    Creates a :class:`HeartbeatService` internally. The scheduler is not
    started on construction -- call :meth:`start()` to begin and
    :meth:`stop()` to shut down gracefully.

    Args:
        cluster_id: The cluster identity to include in each heartbeat.
    """

    def __init__(self, cluster_id: str) -> None:
        self._cluster_id: str = cluster_id
        self._service: HeartbeatService = HeartbeatService(cluster_id=cluster_id)
        self._scheduler: BackgroundScheduler = BackgroundScheduler()

    def _tick(self) -> None:
        """Internal callback fired by APScheduler on each interval."""
        settings = get_settings()
        if settings.sentinel.mock_mode:
            logger.info(
                "mock_heartbeat_tick",
                cluster_id=self._cluster_id,
            )
            return
        self._service.send_heartbeat()

    def start(self) -> None:
        """Add the heartbeat job to the scheduler and start it.

        The interval is read from ``settings.heartbeat.interval_seconds``.
        In mock mode the tick is logged but no HTTP call is made.
        """
        settings = get_settings()
        interval = settings.heartbeat.interval_seconds

        self._scheduler.add_job(
            self._tick,
            trigger="interval",
            seconds=interval,
            id="heartbeat",
            name="Agent heartbeat",
        )
        self._scheduler.start()
        logger.info(
            "heartbeat_scheduler_started",
            interval_seconds=interval,
            mock_mode=settings.sentinel.mock_mode,
        )

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        self._scheduler.shutdown(wait=False)
        logger.info("heartbeat_scheduler_stopped")

    @property
    def running(self) -> bool:
        """Whether the scheduler is currently running."""
        return self._scheduler.running  # type: ignore[no-any-return]

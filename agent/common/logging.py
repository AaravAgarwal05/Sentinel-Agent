"""Structured JSON logging configuration."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structured JSON logging for the agent.

    Emits one JSON object per log event to stdout, including a UTC
    ISO-8601 timestamp, the log level, the logger name, and the event
    payload.

    Args:
        log_level: One of "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL".
            Case-insensitive; unknown values fall back to "INFO".
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Route stdlib logging through stdout; structlog owns the rendering.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a configured structured logger bound to ``name``."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]

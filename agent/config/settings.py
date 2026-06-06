"""Runtime settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Runtime configuration for the Sentinel Agent.

    Settings are loaded from environment variables prefixed with
    ``SENTINEL_`` (e.g. ``SENTINEL_LOG_LEVEL=DEBUG``) and, optionally,
    from a ``.env`` file at the project root.
    """

    model_config = SettingsConfigDict(
        env_prefix="SENTINEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    agent_name: str = Field(default="sentinel-agent")
    agent_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")
    log_level: LogLevel = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()

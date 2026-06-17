"""Hierarchical configuration for the Sentinel Agent.

Phase 1 replaces the flat ``Settings`` model with a four-domain
configuration hierarchy. Each domain is its own Pydantic model with
domain-specific validation; the root :class:`Settings` composes them
and exposes a single :func:`get_settings` accessor for the rest of
the codebase.

Settings are loaded from environment variables only. File-based
loading (YAML, TOML, etc.) is intentionally deferred to a future
phase. Environment variable names follow the convention
``SENTINEL_<DOMAIN>_<FIELD>`` and map to the nested structure via
``settings.<domain>.<field>`` -- e.g.
``SENTINEL_HEARTBEAT_INTERVAL_SECONDS`` populates
``settings.heartbeat.interval_seconds``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Public type aliases for the configuration domain. They live at
# module scope so the rest of the codebase can import them as needed.
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Environment = Literal["development", "staging", "production"]


class AgentConfig(BaseModel):
    """Identity and deployment metadata for the agent instance."""

    name: str = Field(default="sentinel-agent")
    version: str = Field(default="0.1.0")
    cluster_name: str = Field(default="default")
    environment: Environment = Field(default="development")


class SentinelConfig(BaseModel):
    """Connection details for the Sentinel control plane."""

    api_url: str = Field(
        default="https://api.sentinel.example.com",
        min_length=1,
    )
    registration_token: str = Field(default="")
    mock_mode: bool = Field(default=True)


class HeartbeatConfig(BaseModel):
    """Heartbeat transmission settings."""

    interval_seconds: int = Field(default=30, gt=0)


class RuntimeConfig(BaseModel):
    """Runtime behavior settings for the agent process."""

    log_level: LogLevel = Field(default="INFO")


class StorageConfig(BaseModel):
    """Local persistence layer connection settings."""

    database_url: str = Field(default="sqlite:///./sentinel_agent.db", min_length=1)


# Mapping of root config domain -> list of leaf field names. Drives
# ``_SentinelEnvSource`` so the env var ``SENTINEL_<DOMAIN>_<FIELD>``
# resolves to ``settings.<domain>.<field>``.
_FIELD_MAP: dict[str, list[str]] = {
    "agent": ["name", "version", "cluster_name", "environment"],
    "sentinel": ["api_url", "registration_token", "mock_mode"],
    "heartbeat": ["interval_seconds"],
    "runtime": ["log_level"],
    "storage": ["database_url"],
}

_ENV_PREFIX = "SENTINEL_"


class _SentinelEnvSource(PydanticBaseSettingsSource):
    """Env source that flattens ``SENTINEL_<DOMAIN>_<FIELD>`` into nested config.

    Pydantic-settings' built-in env source splits env var names on a
    single delimiter and assumes the resulting path matches the model
    field hierarchy. Our convention is
    ``SENTINEL_<DOMAIN>_<FIELD_WITH_UNDERSCORES>``, which doesn't
    survive a naive split -- e.g. ``SENTINEL_HEARTBEAT_INTERVAL_SECONDS``
    would otherwise map to ``heartbeat.interval.seconds`` rather than
    the field ``heartbeat.interval_seconds``. This source matches the
    known domain prefix and treats the remaining suffix as a single
    leaf field name.
    """

    def __call__(self) -> dict[str, Any]:
        data: dict[str, dict[str, Any]] = {}
        for env_name, env_value in os.environ.items():
            if not env_name.startswith(_ENV_PREFIX):
                continue
            suffix = env_name[len(_ENV_PREFIX) :].lower()
            for domain, leaf_fields in _FIELD_MAP.items():
                token = domain + "_"
                if not suffix.startswith(token):
                    continue
                leaf = suffix[len(token) :]
                if leaf in leaf_fields:
                    data.setdefault(domain, {})[leaf] = env_value
                    break
        return data

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        """Field-level accessor -- unused; values flow through ``__call__``."""
        return None, field_name, False


class Settings(BaseSettings):
    """Root configuration composed of hierarchical sub-configs.

    Access nested values through the sub-configs:

        settings.agent.cluster_name
        settings.sentinel.api_url
        settings.heartbeat.interval_seconds
        settings.runtime.log_level
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    agent: AgentConfig = Field(default_factory=AgentConfig)
    sentinel: SentinelConfig = Field(default_factory=SentinelConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, _SentinelEnvSource(settings_cls))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()

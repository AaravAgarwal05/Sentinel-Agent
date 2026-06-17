"""Payload and response models for Sentinel agent registration."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RegistrationPayload(BaseModel):
    """Payload sent to the Sentinel control plane to register an agent."""

    cluster_id: str
    cluster_name: str
    agent_version: str
    kubernetes_version: str | None = None
    node_count: int | None = None
    namespace_count: int | None = None
    registration_token: str


class RegistrationResponse(BaseModel):
    """Response returned by the Sentinel control plane after successful registration."""

    agent_id: str
    api_key: str
    api_url: str
    expires_at: datetime | None = None
    cluster_id: str

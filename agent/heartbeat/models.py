"""Payload model for agent heartbeat."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HeartbeatPayload(BaseModel):
    """Payload sent to the Sentinel control plane as a liveness signal.

    Attributes:
        cluster_id: Unique identifier for the cluster sending the heartbeat.
        agent_version: Version string of the running agent.
        status: Liveness status (default ``"ok"``).
    """

    cluster_id: str
    agent_version: str
    status: str = Field(default="ok")

"""Pydantic models for detection domain."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from agent.detection.incident import IncidentSeverity, IncidentStatus


class IncidentCandidate(BaseModel):
    incident_type: str
    severity: IncidentSeverity
    namespace: str
    resource_kind: str
    resource_name: str
    message: str


class IncidentResponse(BaseModel):
    id: str
    incident_type: str
    severity: IncidentSeverity
    namespace: str
    resource_kind: str
    resource_name: str
    message: str
    first_seen_at: datetime
    last_seen_at: datetime
    status: IncidentStatus

"""Orchestrates all collectors for a given incident."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agent.collection.collectors.base import Collector, ContextResult, sanitize_payload
from agent.collection.collectors.deployment import DeploymentContextCollector
from agent.collection.collectors.events import EventsContextCollector
from agent.collection.collectors.namespace import NamespaceContextCollector
from agent.collection.collectors.node import NodeContextCollector
from agent.collection.collectors.pod import PodContextCollector
from agent.collection.collectors.replicaset import ReplicaSetContextCollector
from agent.collection.models import ContextType, IncidentContext
from agent.collection.repositories import IncidentContextRepository
from agent.common.logging import get_logger
from agent.storage.database import DatabaseManager

if TYPE_CHECKING:
    from agent.detection.incident import Incident

_logger = get_logger("agent.collection.service")

_COLLECTOR_KEYS: dict[type[Collector], str] = {
    PodContextCollector: "pod",
    DeploymentContextCollector: "deployment",
    ReplicaSetContextCollector: "replicaset",
    NamespaceContextCollector: "namespace",
    EventsContextCollector: "events",
    NodeContextCollector: "node",
}


def _resolve_collector_key(collector: Collector) -> str:
    """Return the context-type key for *collector* using ``isinstance``.

    Using ``isinstance`` rather than ``type()`` look-up allows test mocks
    to substitute for any collector class without type identity.
    """
    for cls, key in _COLLECTOR_KEYS.items():
        if isinstance(collector, cls):
            return key
    return "unknown"


@dataclass
class IncidentContextPackage:
    """Aggregated context data collected for a single incident."""

    incident: Incident
    pod: dict | None = None
    deployment: dict | None = None
    replicaset: dict | None = None
    namespace: dict | None = None
    events: dict | None = None
    node: dict | None = None


class CollectionService:
    """Orchestrates all collectors for a given incident."""

    def __init__(self, db: DatabaseManager) -> None:
        """Initialise the service with collectors and the repository.

        Collectors are lazily initialised to avoid Kubernetes API config
        loading at construction time (relevant in test environments
        without a cluster).

        Args:
            db: A ``DatabaseManager`` instance used for session management
                and passed to the ``IncidentContextRepository``.
        """
        self._db = db
        self._collectors: list[Collector] | None = None
        self._repository = IncidentContextRepository(db)

    def collect_for_incident(
        self, incident: Incident, pod: dict | None = None
    ) -> IncidentContextPackage:
        """Collect context from all collectors, persist, return package.

        Each collector runs independently. Failures are logged but do NOT
        stop collection of other context types.

        When *pod* is ``None`` (e.g. called from the poller path that
        does not have access to the full pod object), collection is
        skipped.

        Args:
            incident: The incident to collect context for.
            pod: Pod dict from the Kubernetes API (snake_case keys via
                 ``to_dict()``).

        Returns:
            An ``IncidentContextPackage`` with the collected context. Fields
            will be ``None`` for collectors that returned ``None`` or raised
            an error.
        """
        if pod is None:
            _logger.info(
                "context_collection_skipped_no_pod",
                incident_id=incident.id,
                incident_type=incident.incident_type,
                resource_name=incident.resource_name,
            )
            return IncidentContextPackage(incident=incident)

        namespace = incident.namespace
        name = incident.resource_name

        _logger.info(
            "context_collection_started",
            incident_id=incident.id,
            incident_type=incident.incident_type,
            resource_name=name,
        )

        payloads = self._run_collectors(
            pod, namespace, name,
            incident_id=incident.id,
            incident_type=incident.incident_type,
        )

        records: list[IncidentContext] = []
        for ctx_type_str, ctx_payload in payloads.items():
            if ctx_payload is None:
                continue
            try:
                context_type = ContextType(ctx_type_str.upper())
            except ValueError:
                _logger.warning("Unknown context type string: %s", ctx_type_str)
                continue

            records.append(
                IncidentContext(
                    incident_id=incident.id,
                    context_type=context_type,
                    context_payload=sanitize_payload(ctx_payload),
                    collected_at=datetime.now(UTC),
                )
            )

        if records:
            with self._db.session() as session:
                for record in records:
                    self._repository.create(session, record)
            _logger.info(
                "context_collected",
                incident_id=incident.id,
                incident_type=incident.incident_type,
                resource_name=name,
                context_count=len(records),
            )

        return IncidentContextPackage(
            incident=incident,
            pod=payloads.get("pod"),
            deployment=payloads.get("deployment"),
            replicaset=payloads.get("replicaset"),
            namespace=payloads.get("namespace"),
            events=payloads.get("events"),
            node=payloads.get("node"),
        )

    def _run_collectors(
        self,
        pod: dict,
        namespace: str,
        name: str,
        incident_id: str = "",
        incident_type: str = "",
    ) -> dict[str, Any]:
        """Run all collectors, catch per-collector failures, return payload dict.

        Args:
            pod: Pod dict from the Kubernetes API.
            namespace: The pod's namespace.
            name: The pod's name.
            incident_id: Incident ID for structured logging.
            incident_type: Incident type for structured logging.

        Returns:
            A dict keyed by context type (``"pod"``, ``"deployment"``, etc.)
            with the collector's ``context_payload``, or ``None`` when the
            collector returned ``None`` or raised an exception.
        """
        results: dict[str, Any] = {}

        for collector in self._get_collectors():
            key = _resolve_collector_key(collector)
            try:
                result: ContextResult | None = collector.collect(pod, namespace, name)
                results[key] = result.context_payload if result is not None else None
            except Exception:
                _logger.exception(
                    "context_collection_failed",
                    incident_id=incident_id,
                    incident_type=incident_type,
                    resource_name=name,
                )
                results[key] = None

        return results

    def _get_collectors(self) -> list[Collector]:
        """Return the list of context collectors, initialising lazily."""
        if self._collectors is None:
            self._collectors = [
                PodContextCollector(),
                DeploymentContextCollector(),
                ReplicaSetContextCollector(),
                NamespaceContextCollector(),
                EventsContextCollector(),
                NodeContextCollector(),
            ]
        return self._collectors

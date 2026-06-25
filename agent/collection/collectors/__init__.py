"""Collector registry and base interface."""

from agent.collection.collectors.base import Collector, ContextResult
from agent.collection.collectors.events import EventsContextCollector
from agent.collection.collectors.node import NodeContextCollector
from agent.collection.collectors.pod import PodContextCollector
from agent.collection.collectors.replicaset import ReplicaSetContextCollector

__all__ = [
    "Collector",
    "ContextResult",
    "EventsContextCollector",
    "NodeContextCollector",
    "PodContextCollector",
    "ReplicaSetContextCollector",
]

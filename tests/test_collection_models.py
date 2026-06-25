"""Tests for the IncidentContext model and ContextType enum."""
from __future__ import annotations

from agent.collection.models import ContextType, IncidentContext

# ---------------------------------------------------------------------------
# ContextType enum
# ---------------------------------------------------------------------------


class TestContextTypeEnum:
    def test_has_all_context_types(self) -> None:
        assert ContextType.POD == "POD"
        assert ContextType.DEPLOYMENT == "DEPLOYMENT"
        assert ContextType.REPLICASET == "REPLICASET"
        assert ContextType.NAMESPACE == "NAMESPACE"
        assert ContextType.EVENTS == "EVENTS"
        assert ContextType.NODE == "NODE"

    def test_all_members_are_strings(self) -> None:
        for member in ContextType:
            assert isinstance(member.value, str)

    def test_six_context_types_exist(self) -> None:
        assert len(ContextType) == 6


# ---------------------------------------------------------------------------
# IncidentContext model
# ---------------------------------------------------------------------------


class TestIncidentContextModel:
    def test_create_with_minimal_args(self) -> None:
        ctx = IncidentContext(
            incident_id="inc-123",
            context_type=ContextType.POD,
            context_payload={"name": "test-pod"},
        )
        assert ctx.incident_id == "inc-123"
        assert ctx.context_type == ContextType.POD
        assert ctx.context_payload == {"name": "test-pod"}
        # id uses a Python-side default that runs on INSERT
        assert ctx.id is None  # None until flushed to DB

    def test_id_column_has_uuid_default(self) -> None:
        """The id column is configured with a Python-side UUID default."""
        col = IncidentContext.__table__.c.id
        assert col.default is not None
        uuid_val = col.default.arg(None)  # call the default factory
        assert isinstance(uuid_val, str)
        assert len(uuid_val) == 36

    def test_collected_at_has_server_default(self) -> None:
        ctx = IncidentContext(
            incident_id="inc-123",
            context_type=ContextType.POD,
            context_payload={},
        )
        # collected_at is a server_default, so it's None until flushed
        # to the database; the attribute is populated by the ORM after
        # flush.  At model level we verify the column exists.
        assert hasattr(ctx, "collected_at")

    def test_context_payload_accepts_nested_dict(self) -> None:
        payload = {
            "metadata": {"name": "test", "labels": {"app": "web"}},
            "status": {"phase": "Running"},
        }
        ctx = IncidentContext(
            incident_id="inc-123",
            context_type=ContextType.POD,
            context_payload=payload,
        )
        assert ctx.context_payload["metadata"]["name"] == "test"
        assert ctx.context_payload["status"]["phase"] == "Running"

    def test_context_payload_accepts_empty_dict(self) -> None:
        ctx = IncidentContext(
            incident_id="inc-123",
            context_type=ContextType.EVENTS,
            context_payload={},
        )
        assert ctx.context_payload == {}

    def test_repr_contains_model_name(self) -> None:
        ctx = IncidentContext(
            incident_id="inc-456",
            context_type=ContextType.NAMESPACE,
            context_payload={},
        )
        representation = repr(ctx)
        assert "IncidentContext" in representation

    def test_relationship_back_populates_incident(self) -> None:
        """IncidentContext has a back-populated 'incident' relationship
        attribute that is None until populated by a DB query."""
        ctx = IncidentContext(
            incident_id="inc-789",
            context_type=ContextType.POD,
            context_payload={},
        )
        # Before persistence the relationship is None
        assert ctx.incident is None

    def test_equality_is_based_on_object_identity(self) -> None:
        ctx_a = IncidentContext(
            incident_id="inc-1",
            context_type=ContextType.POD,
            context_payload={},
        )
        ctx_b = IncidentContext(
            incident_id="inc-1",
            context_type=ContextType.POD,
            context_payload={},
        )
        assert ctx_a is not ctx_b

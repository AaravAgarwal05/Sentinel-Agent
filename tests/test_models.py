"""Tests for the SQLAlchemy ORM models."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import ColumnDefault

from agent.storage.models import Base, ClusterIdentity, Credentials, HeartbeatRecord


def test_base_is_declarative_base() -> None:
    """``Base`` is an instance of ``DeclarativeBase``."""
    assert isinstance(Base, type) and issubclass(Base, DeclarativeBase)


def test_cluster_identity_has_correct_table_name() -> None:
    """``ClusterIdentity`` uses ``cluster_identity`` as its table name."""
    assert ClusterIdentity.__tablename__ == "cluster_identity"


def test_cluster_identity_has_expected_columns() -> None:
    """``ClusterIdentity`` defines the expected set of column names."""
    mapper = ClusterIdentity.__mapper__
    columns = {c.name for c in mapper.columns}
    expected = {
        "id",
        "cluster_id",
        "cluster_name",
        "agent_version",
        "kubernetes_version",
        "node_count",
        "namespace_count",
        "registered_at",
        "last_seen_at",
    }
    assert columns == expected


def test_cluster_identity_non_nullable_columns() -> None:
    """The required (non-nullable) columns are enforced."""
    mapper = ClusterIdentity.__mapper__
    for col_name in ("id", "cluster_id", "cluster_name", "agent_version"):
        assert not mapper.columns[col_name].nullable, f"{col_name} should be non-nullable"


def test_cluster_identity_nullable_columns() -> None:
    """The optional (nullable) columns are correctly marked."""
    mapper = ClusterIdentity.__mapper__
    for col_name in ("kubernetes_version", "node_count", "namespace_count"):
        assert mapper.columns[col_name].nullable, f"{col_name} should be nullable"


def test_cluster_identity_has_autoincrement_pk() -> None:
    """``ClusterIdentity.id`` is an auto-increment primary key."""
    col = ClusterIdentity.__mapper__.columns["id"]
    assert col.primary_key
    assert col.autoincrement is True


def test_cluster_identity_cluster_id_is_unique() -> None:
    """``ClusterIdentity.cluster_id`` has a unique constraint."""
    col = ClusterIdentity.__mapper__.columns["cluster_id"]
    assert col.unique is True


def test_cluster_identity_registered_at_has_server_default() -> None:
    """``registered_at`` has a server_default set (not None)."""
    col = ClusterIdentity.__mapper__.columns["registered_at"]
    assert col.server_default is not None


def test_cluster_identity_last_seen_at_has_onupdate() -> None:
    """``last_seen_at`` has server_default and onupdate set."""
    col = ClusterIdentity.__mapper__.columns["last_seen_at"]
    assert col.server_default is not None
    assert col.onupdate is not None


def test_credentials_has_correct_table_name() -> None:
    """``Credentials`` uses ``credentials`` as its table name."""
    assert Credentials.__tablename__ == "credentials"


def test_credentials_has_expected_columns() -> None:
    """``Credentials`` defines the expected set of column names."""
    mapper = Credentials.__mapper__
    columns = {c.name for c in mapper.columns}
    expected = {
        "id",
        "agent_id",
        "api_key",
        "api_url",
        "expires_at",
        "created_at",
    }
    assert columns == expected


def test_credentials_non_nullable_columns() -> None:
    """The required columns are correctly marked non-nullable."""
    mapper = Credentials.__mapper__
    for col_name in ("id", "agent_id", "api_key", "api_url"):
        assert not mapper.columns[col_name].nullable, f"{col_name} should be non-nullable"


def test_credentials_expires_at_nullable() -> None:
    """``expires_at`` is nullable (credentials may not have an expiry)."""
    assert Credentials.__mapper__.columns["expires_at"].nullable is True


def test_credentials_created_at_has_server_default() -> None:
    """``created_at`` has a server_default set."""
    col = Credentials.__mapper__.columns["created_at"]
    assert col.server_default is not None


def test_heartbeat_record_has_correct_table_name() -> None:
    """``HeartbeatRecord`` uses ``heartbeat_record`` as its table name."""
    assert HeartbeatRecord.__tablename__ == "heartbeat_record"


def test_heartbeat_record_has_expected_columns() -> None:
    """``HeartbeatRecord`` defines the expected set of column names."""
    mapper = HeartbeatRecord.__mapper__
    columns = {c.name for c in mapper.columns}
    expected = {
        "id",
        "cluster_id",
        "agent_version",
        "status",
        "sent_at",
    }
    assert columns == expected


def test_heartbeat_record_non_nullable_columns() -> None:
    """The required columns are correctly marked non-nullable."""
    mapper = HeartbeatRecord.__mapper__
    for col_name in ("id", "cluster_id", "agent_version"):
        assert not mapper.columns[col_name].nullable, f"{col_name} should be non-nullable"


def test_heartbeat_record_status_default() -> None:
    """``status`` defaults to ``"ok"``."""
    col = HeartbeatRecord.__mapper__.columns["status"]
    assert col.default is not None
    assert isinstance(col.default, ColumnDefault)
    assert col.default.arg == "ok"


def test_heartbeat_record_sent_at_has_server_default() -> None:
    """``sent_at`` has a server_default set."""
    col = HeartbeatRecord.__mapper__.columns["sent_at"]
    assert col.server_default is not None

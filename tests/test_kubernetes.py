"""Tests for the Kubernetes client."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from kubernetes.config.config_exception import ConfigException

from agent.common.kubernetes import KubernetesClient


def _make_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make both in-cluster and kubeconfig config loading raise."""
    monkeypatch.setattr(
        "agent.common.kubernetes.k8s_config.load_incluster_config",
        MagicMock(side_effect=ConfigException("not in cluster")),
    )
    monkeypatch.setattr(
        "agent.common.kubernetes.k8s_config.load_kube_config",
        MagicMock(side_effect=ConfigException("no kubeconfig")),
    )


def _mock_successful_config(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock]:
    """Patch config loading and API constructors to simulate successful auth.

    Returns the mocked ``CoreV1Api`` and ``VersionApi`` instances so
    callers can attach side-effects for individual method calls.

    Uses ``monkeypatch`` so patches survive for the full test function.
    """
    mock_core = MagicMock()
    mock_version = MagicMock()

    monkeypatch.setattr(
        "agent.common.kubernetes.k8s_config.load_incluster_config",
        MagicMock(),
    )
    monkeypatch.setattr(
        "agent.common.kubernetes.k8s_client.CoreV1Api",
        MagicMock(return_value=mock_core),
    )
    monkeypatch.setattr(
        "agent.common.kubernetes.k8s_client.VersionApi",
        MagicMock(return_value=mock_version),
    )

    return mock_core, mock_version


# ---------------------------------------------------------------------------
# Unavailable client
# ---------------------------------------------------------------------------


def test_client_unavailable_when_no_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """``KubernetesClient`` is unavailable when neither in-cluster
    nor kubeconfig works."""
    _make_unavailable(monkeypatch)
    client = KubernetesClient()
    assert client.available is False


def test_get_cluster_version_returns_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_cluster_version()`` returns ``None`` when the client is
    unavailable."""
    _make_unavailable(monkeypatch)
    client = KubernetesClient()
    result = client.get_cluster_version()
    assert result is None


def test_get_node_count_returns_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_node_count()`` returns ``None`` when the client is
    unavailable."""
    _make_unavailable(monkeypatch)
    client = KubernetesClient()
    result = client.get_node_count()
    assert result is None


def test_get_namespace_count_returns_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_namespace_count()`` returns ``None`` when the client is
    unavailable."""
    _make_unavailable(monkeypatch)
    client = KubernetesClient()
    result = client.get_namespace_count()
    assert result is None


# ---------------------------------------------------------------------------
# Available client — in-cluster auth
# ---------------------------------------------------------------------------


def test_available_client_has_version_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An available ``KubernetesClient`` has both ``_api`` and ``_version_api``."""
    mock_core, mock_version = _mock_successful_config(monkeypatch)
    client = KubernetesClient()
    assert client.available is True
    assert client._api is mock_core
    assert client._version_api is mock_version


def test_get_cluster_version_uses_version_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_cluster_version()`` calls ``VersionApi.get_code()``
    rather than ``CoreV1Api.get_code()``."""
    mock_core, mock_version = _mock_successful_config(monkeypatch)
    mock_version.get_code.return_value = MagicMock(git_version="1.28.3")

    client = KubernetesClient()
    result = client.get_cluster_version()

    assert result == "1.28.3"
    mock_version.get_code.assert_called_once()
    # CoreV1Api should NOT have been called for version
    assert mock_core.get_code.call_count == 0


def test_get_cluster_version_returns_none_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_cluster_version()`` returns ``None`` when the API call fails."""
    _, mock_version = _mock_successful_config(monkeypatch)
    mock_version.get_code.side_effect = Exception("API error")

    client = KubernetesClient()
    result = client.get_cluster_version()

    assert result is None


def test_get_node_count_returns_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_node_count()`` returns the number of nodes."""
    mock_core, _ = _mock_successful_config(monkeypatch)
    mock_core.list_node.return_value = MagicMock(items=["node1", "node2", "node3"])

    client = KubernetesClient()
    result = client.get_node_count()

    assert result == 3
    mock_core.list_node.assert_called_once()


def test_get_node_count_returns_none_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_node_count()`` returns ``None`` when the API call fails."""
    mock_core, _ = _mock_successful_config(monkeypatch)
    mock_core.list_node.side_effect = Exception("API error")

    client = KubernetesClient()
    result = client.get_node_count()

    assert result is None


def test_get_namespace_count_returns_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_namespace_count()`` returns the number of namespaces."""
    mock_core, _ = _mock_successful_config(monkeypatch)
    mock_core.list_namespace.return_value = MagicMock(
        items=["ns1", "ns2", "ns3", "ns4"]
    )

    client = KubernetesClient()
    result = client.get_namespace_count()

    assert result == 4
    mock_core.list_namespace.assert_called_once()


def test_get_namespace_count_returns_none_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_namespace_count()`` returns ``None`` when the API call fails."""
    mock_core, _ = _mock_successful_config(monkeypatch)
    mock_core.list_namespace.side_effect = Exception("API error")

    client = KubernetesClient()
    result = client.get_namespace_count()

    assert result is None


def test_all_metadata_methods_work_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration-style test: simulate a real cluster session where all
    three metadata calls succeed."""
    mock_core, mock_version = _mock_successful_config(monkeypatch)

    mock_version.get_code.return_value = MagicMock(git_version="1.30.0")
    mock_core.list_node.return_value = MagicMock(items=["n1", "n2"])
    mock_core.list_namespace.return_value = MagicMock(items=["ns1", "ns2", "ns3"])

    client = KubernetesClient()

    assert client.get_cluster_version() == "1.30.0"
    assert client.get_node_count() == 2
    assert client.get_namespace_count() == 3
    mock_version.get_code.assert_called_once()
    mock_core.list_node.assert_called_once()
    mock_core.list_namespace.assert_called_once()

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


def test_get_cluster_version_returns_none_on_api_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_cluster_version()`` returns ``None`` when the API call raises."""
    _make_unavailable(monkeypatch)
    client = KubernetesClient()
    assert client.available is False
    result = client.get_cluster_version()
    assert result is None


def test_get_node_count_returns_none_on_api_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_node_count()`` returns ``None`` when the API call raises."""
    _make_unavailable(monkeypatch)
    client = KubernetesClient()
    assert client.available is False
    result = client.get_node_count()
    assert result is None


def test_get_namespace_count_returns_none_on_api_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_namespace_count()`` returns ``None`` when the API call raises."""
    _make_unavailable(monkeypatch)
    client = KubernetesClient()
    assert client.available is False
    result = client.get_namespace_count()
    assert result is None

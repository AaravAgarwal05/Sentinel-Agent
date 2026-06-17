"""Tests for Helm chart rendering, Dockerfile, and runtime health module."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from agent.runtime import health

# ---------------------------------------------------------------------------
# Helm chart tests
# ---------------------------------------------------------------------------

helm_available = shutil.which("helm") is not None
skipif_no_helm = pytest.mark.skipif(
    not helm_available, reason="helm CLI not found on PATH"
)

pytestmark = [
    pytest.mark.helm,
    skipif_no_helm,
]

_CHART_PATH = Path("charts/sentinel-agent")

_EXPECTED_RESOURCES: dict[str, str] = {
    "Deployment": "sentinel-agent",
    "ServiceAccount": "sentinel-agent",
    "Role": "sentinel-agent-role",
    "RoleBinding": "sentinel-agent-rolebinding",
    "ConfigMap": "sentinel-agent-config",
    "Secret": "sentinel-agent-secret",
}

_EXPECTED_CONFIGMAP_KEYS: list[str] = [
    "SENTINEL_AGENT_CLUSTER_NAME",
    "SENTINEL_SENTINEL_API_URL",
    "SENTINEL_SENTINEL_MOCK_MODE",
    "SENTINEL_HEARTBEAT_INTERVAL_SECONDS",
    "SENTINEL_RUNTIME_LOG_LEVEL",
    "SENTINEL_STORAGE_DATABASE_URL",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_chart(values: list[str] | None = None) -> list[dict]:
    """Run ``helm template`` and return the parsed list of Kubernetes resources."""
    cmd = ["helm", "template", "sentinel-agent", str(_CHART_PATH)]
    if values:
        cmd.extend(values)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return list(yaml.safe_load_all(result.stdout))


def _collect_resources(docs: list[dict]) -> dict[tuple[str, str], dict]:
    """Index rendered documents by ``(Kind, name)``."""
    resources: dict[tuple[str, str], dict] = {}
    for doc in docs:
        if doc is None:
            continue
        kind = doc.get("kind")
        name = doc.get("metadata", {}).get("name")
        if kind and name:
            resources[(kind, name)] = doc
    return resources


# ---------------------------------------------------------------------------
# Chart lint
# ---------------------------------------------------------------------------


def test_helm_lint() -> None:
    """Chart passes ``helm lint``."""
    result = subprocess.run(
        ["helm", "lint", str(_CHART_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"helm lint failed:\n{result.stdout}\n{result.stderr}"


# ---------------------------------------------------------------------------
# Default template
# ---------------------------------------------------------------------------


def test_helm_template_defaults() -> None:
    """Default template produces all expected resources."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    for kind, name in _EXPECTED_RESOURCES.items():
        assert (kind, name) in resources, (
            f"Missing resource {kind}/{name}"
        )


def test_deployment_container() -> None:
    """Deployment container spec matches expectations."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    deployment = resources[("Deployment", "sentinel-agent")]
    containers = deployment["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1
    container = containers[0]

    assert container["image"] == "sentinel-agent:latest"
    assert container["command"] == ["python"]
    assert container["args"] == ["-m", "src.main"]

    env_from = container.get("envFrom", [])
    config_map_refs = [
        ef for ef in env_from if "configMapRef" in ef
    ]
    secret_refs = [
        ef for ef in env_from if "secretRef" in ef
    ]
    assert len(config_map_refs) == 1
    assert config_map_refs[0]["configMapRef"]["name"] == "sentinel-agent-config"
    assert len(secret_refs) == 1
    assert secret_refs[0]["secretRef"]["name"] == "sentinel-agent-secret"


def test_deployment_probes() -> None:
    """Deployment has liveness and readiness probes with exec commands."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    deployment = resources[("Deployment", "sentinel-agent")]
    container = deployment["spec"]["template"]["spec"]["containers"][0]

    liveness = container.get("livenessProbe")
    assert liveness is not None, "Missing livenessProbe"
    exec_cmd = liveness.get("exec", {}).get("command", [])
    assert len(exec_cmd) > 0

    readiness = container.get("readinessProbe")
    assert readiness is not None, "Missing readinessProbe"
    exec_cmd = readiness.get("exec", {}).get("command", [])
    assert len(exec_cmd) > 0


def test_deployment_resources() -> None:
    """Deployment container has resource limits and requests."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    deployment = resources[("Deployment", "sentinel-agent")]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    resources_block = container.get("resources")

    assert resources_block is not None, "Missing resources block"
    assert "limits" in resources_block, "Missing resource limits"
    assert "requests" in resources_block, "Missing resource requests"


def test_configmap_env_vars() -> None:
    """ConfigMap contains all expected environment variable keys."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    configmap = resources[("ConfigMap", "sentinel-agent-config")]
    data = configmap.get("data", {})

    for key in _EXPECTED_CONFIGMAP_KEYS:
        assert key in data, f"Missing ConfigMap key: {key}"


def test_secret_contains_token() -> None:
    """Secret contains the ``sentinel-registration-token`` key."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    secret = resources[("Secret", "sentinel-agent-secret")]
    data = secret.get("data", {})
    assert "sentinel-registration-token" in data, (
        "Missing sentinel-registration-token in Secret"
    )


def test_rbac_role() -> None:
    """Role defines correct readonly rules."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    role = resources[("Role", "sentinel-agent-role")]
    rules = role.get("rules", [])
    assert len(rules) > 0

    readonly_verbs = {"get", "list", "watch"}
    for rule in rules:
        verbs = set(rule.get("verbs", []))
        assert verbs.issubset(readonly_verbs), (
            f"Role rule uses non-readonly verbs: {verbs - readonly_verbs}"
        )


def test_rbac_rolebinding() -> None:
    """RoleBinding binds the correct ServiceAccount."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    binding = resources[("RoleBinding", "sentinel-agent-rolebinding")]

    subjects = binding.get("subjects", [])
    assert len(subjects) == 1
    assert subjects[0]["kind"] == "ServiceAccount"
    assert subjects[0]["name"] == "sentinel-agent"

    role_ref = binding.get("roleRef", {})
    assert role_ref.get("kind") == "Role"
    assert role_ref.get("name") == "sentinel-agent-role"


def test_serviceaccount_exists() -> None:
    """ServiceAccount is named ``sentinel-agent``."""
    docs = _render_chart()
    resources = _collect_resources(docs)
    sa = resources[("ServiceAccount", "sentinel-agent")]
    assert sa["metadata"]["name"] == "sentinel-agent"


# ---------------------------------------------------------------------------
# Custom values
# ---------------------------------------------------------------------------


def test_helm_template_custom_values() -> None:
    """Custom values are reflected in the rendered ConfigMap."""
    overrides = [
        "--set", "sentinel.mockMode=false",
        "--set", "sentinel.apiUrl=https://custom.example.com",
    ]
    docs = _render_chart(overrides)
    resources = _collect_resources(docs)
    configmap = resources[("ConfigMap", "sentinel-agent-config")]
    data = configmap.get("data", {})

    assert data.get("SENTINEL_SENTINEL_MOCK_MODE") == "false", (
        "sentinel.mockMode override not reflected"
    )
    assert data.get("SENTINEL_SENTINEL_API_URL") == "https://custom.example.com", (
        "sentinel.apiUrl override not reflected"
    )


# ---------------------------------------------------------------------------
# Dockerfile tests
# ---------------------------------------------------------------------------


def test_dockerfile_exists() -> None:
    """Dockerfile exists and is non-empty."""
    dockerfile = Path("Dockerfile")
    assert dockerfile.exists(), "Dockerfile not found"
    assert dockerfile.stat().st_size > 0, "Dockerfile is empty"


def test_dockerfile_multistage() -> None:
    """Dockerfile uses multi-stage build (builder + runtime)."""
    content = Path("Dockerfile").read_text()
    assert "FROM" in content
    assert "AS builder" in content or "as builder" in content
    assert "AS runtime" in content or "as runtime" in content


def test_dockerfile_nonroot() -> None:
    """Dockerfile sets a non-root user."""
    content = Path("Dockerfile").read_text()
    assert "USER sentinel" in content or "USER 1000" in content


def test_dockerignore_exists() -> None:
    """``.dockerignore`` exists next to the Dockerfile."""
    assert Path(".dockerignore").exists(), ".dockerignore not found"


# ---------------------------------------------------------------------------
# Health module tests
# ---------------------------------------------------------------------------


def test_health_unhealthy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``is_healthy()`` returns ``False`` when the marker file does not exist."""
    missing_path = tmp_path / "nonexistent-marker"
    monkeypatch.setattr(health, "MARKER_PATH", missing_path)
    assert health.is_healthy() is False


def test_health_healthy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``is_healthy()`` returns ``True`` when the marker file exists."""
    marker = tmp_path / "ready"
    marker.write_text("")
    monkeypatch.setattr(health, "MARKER_PATH", marker)
    assert health.is_healthy() is True


def test_health_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``is_ready()`` mirrors ``is_healthy()`` behavior."""
    # When marker does not exist
    missing = tmp_path / "no-marker"
    monkeypatch.setattr(health, "MARKER_PATH", missing)
    assert health.is_ready() is False

    # When marker exists
    marker = tmp_path / "ready-marker"
    marker.write_text("")
    monkeypatch.setattr(health, "MARKER_PATH", marker)
    assert health.is_ready() is True

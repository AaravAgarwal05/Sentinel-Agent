"""Service orchestrating agent registration with Sentinel."""
from __future__ import annotations

import uuid

from agent.common.kubernetes import KubernetesClient
from agent.common.logging import get_logger
from agent.config.settings import get_settings
from agent.registration.client import RegistrationClient
from agent.registration.models import RegistrationPayload, RegistrationResponse
from agent.storage.database import DatabaseManager
from agent.storage.repositories import (
    ClusterIdentityRepository,
    CredentialsRepository,
)

_logger = get_logger("agent.registration.service")


class RegistrationService:
    """Orchestrates the end-to-end registration of a Sentinel Agent.

    Collects cluster metadata (via an optional :class:`KubernetesClient`),
    sends a registration request to the Sentinel control plane, and
    persists the resulting identity and credentials locally.
    """

    def __init__(
        self,
        db: DatabaseManager,
        k8s_client: KubernetesClient | None = None,
    ) -> None:
        """Store dependencies used during registration.

        Args:
            db: The shared database manager for persisting results.
            k8s_client: Optional Kubernetes client for cluster metadata
                collection. When ``None``, cluster metadata fields will
                default to ``None``.
        """
        self._db: DatabaseManager = db
        self._k8s_client: KubernetesClient | None = k8s_client
        self._reg_client: RegistrationClient = RegistrationClient()
        self._settings = get_settings()
        self._identity_repo: ClusterIdentityRepository = ClusterIdentityRepository(db)
        self._credentials_repo: CredentialsRepository = CredentialsRepository(db)

    def register(self) -> RegistrationResponse | None:
        """Collect cluster metadata, register with Sentinel, persist results.

        The registration flow:

        1. Query cluster metadata from the optional ``KubernetesClient``.
        2. Resolve a stable ``cluster_id`` -- use the existing one from the
           database if already registered, otherwise generate a new UUID.
        3. Build a :class:`RegistrationPayload` including the registration
           token from settings.
        4. Call :meth:`RegistrationClient.register` to contact the control
           plane.
        5. On success, persist a :class:`ClusterIdentity` and
           :class:`Credentials` record via the respective repositories.
        6. Return the :class:`RegistrationResponse`.

        Returns:
            The server response on success, or ``None`` if registration
            failed.
        """
        # Step 1: collect cluster metadata
        kubernetes_version: str | None = None
        node_count: int | None = None
        namespace_count: int | None = None

        if self._k8s_client is not None and self._k8s_client.available:
            kubernetes_version = self._k8s_client.get_cluster_version()
            node_count = self._k8s_client.get_node_count()
            namespace_count = self._k8s_client.get_namespace_count()
            _logger.debug(
                "registration_cluster_metadata",
                kubernetes_version=kubernetes_version,
                node_count=node_count,
                namespace_count=namespace_count,
            )
        else:
            _logger.info("registration_no_k8s_client")

        # Step 2: resolve cluster_id
        cluster_id: str = str(uuid.uuid4())

        payload = RegistrationPayload(
            cluster_id=cluster_id,
            cluster_name=self._settings.agent.cluster_name,
            agent_version=self._settings.agent.version,
            kubernetes_version=kubernetes_version,
            node_count=node_count,
            namespace_count=namespace_count,
            registration_token=self._settings.sentinel.registration_token,
        )

        # Step 4: send registration
        response = self._reg_client.register(payload)
        if response is None:
            _logger.error("registration_failed")
            return None

        # Step 5: persist identity and credentials
        try:
            with self._db.session() as session:
                self._identity_repo.create(
                    session=session,
                    cluster_id=cluster_id,
                    cluster_name=self._settings.agent.cluster_name,
                    agent_version=self._settings.agent.version,
                    kubernetes_version=kubernetes_version,
                    node_count=node_count,
                    namespace_count=namespace_count,
                )
                self._credentials_repo.create(
                    session=session,
                    agent_id=response.agent_id,
                    api_key=response.api_key,
                    api_url=response.api_url,
                    expires_at=response.expires_at,
                )
        except Exception:
            _logger.exception("registration_persist_failed")
            return None

        _logger.info(
            "registration_complete",
            cluster_id=cluster_id,
            agent_id=response.agent_id,
        )
        return response

"""
IAM policy management port.

This port abstracts the outbound operations HexShare performs against an
external Identity & Access Management (IAM) provider to grant or revoke
user policies on HexShare-owned resources (e.g. rooms/document groups).

The default implementation targets HexIAM, but any provider can be
plugged in by implementing this interface and registering it with
:class:`~app.infra.factories.IAMPolicyFactory`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional


class IAMPolicyError(Exception):
    """Raised when the IAM provider rejects or fails a policy mutation."""


class IAMPolicyPort(ABC):
    @abstractmethod
    async def grant_policy(
        self,
        *,
        bearer_token: str,
        tenant_id: str,
        user_id: str,
        policy_id: str,
        resource: str,
        actions: list[str],
        conditions: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Grant a policy on ``resource`` to ``user_id``.

        ``actions`` is the IAM provider's vocabulary of action name strings
        (e.g. ``["read", "write", "manage"]``).  Implementations are
        responsible for translating to whatever wire format the IAM
        expects.
        """

    @abstractmethod
    async def revoke_policy(
        self,
        *,
        bearer_token: str,
        tenant_id: str,
        user_id: str,
        policy_id: str,
    ) -> None:
        """Revoke a previously-granted policy from ``user_id``."""

    async def list_tenant_users(
        self,
        *,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("Listing tenant users is not supported by this IAM policy adapter")

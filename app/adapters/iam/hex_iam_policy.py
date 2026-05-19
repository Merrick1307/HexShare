"""
HexIAM policy adapter.

Implements :class:`~app.ports.iam_policy.IAMPolicyPort` against HexIAM's
``/api/v1/policies`` endpoints using service-to-service authentication
via client credentials flow.
"""
from __future__ import annotations

import os
import time
from typing import Any, Mapping, Optional
from urllib.parse import quote

import httpx

from app.infra.factories import IAMPolicyFactory
from app.ports.iam_policy import IAMPolicyError, IAMPolicyPort


class HexIAMPolicyClient(IAMPolicyPort):
    def __init__(
        self,
        *,
        iam_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        raw_url = (iam_url or os.getenv("HEXIAM_URL", "")).rstrip("/")
        self.iam_url = raw_url.replace("localhost", "host.docker.internal")
        self.client_id = client_id or os.getenv("HEXSHARE_PDP_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("HEXSHARE_PDP_CLIENT_SECRET", "")
        self.timeout_s = timeout_s

        self._cached_token: str | None = None
        self._token_expires_at: float = 0

        if not self.iam_url:
            raise RuntimeError("Missing HEXIAM_URL for HexIAMPolicyClient")
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Missing HEXSHARE_PDP_CLIENT_ID or HEXSHARE_PDP_CLIENT_SECRET")

    async def _get_service_token(self) -> str:
        now = time.time()
        if self._cached_token and now < self._token_expires_at - 30:
            return self._cached_token

        url = f"{self.iam_url}/api/v1/oidc/token"
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if r.status_code >= 400:
            raise IAMPolicyError(f"Failed to obtain service token: {r.status_code} {r.text}")

        data = r.json()
        self._cached_token = data["access_token"].strip()
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = now + expires_in
        return self._cached_token

    def _headers(self, token: str, tenant_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-TENANT-ID": tenant_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

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
        service_token = await self._get_service_token()
        url = f"{self.iam_url}/api/v1/policies/user/{quote(user_id, safe='')}?client_id={self.client_id}"
        headers = self._headers(service_token, tenant_id)
        body = {
            "policy_id": policy_id,
            "resource": resource,
            "actions": actions,
            "conditions": dict(conditions) if conditions else {},
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.post(url, json=body, headers=headers)
        if r.status_code >= 400:
            raise IAMPolicyError(
                f"HexIAM grant_policy failed ({r.status_code}): {r.text}"
            )

    async def revoke_policy(
        self,
        *,
        bearer_token: str,
        tenant_id: str,
        user_id: str,
        policy_id: str,
    ) -> None:
        service_token = await self._get_service_token()
        url = f"{self.iam_url}/api/v1/policies/user/{quote(user_id, safe='')}/{quote(policy_id, safe='')}?client_id={self.client_id}"
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.delete(url, headers=self._headers(service_token, tenant_id))
        if r.status_code not in (200, 204, 404):
            raise IAMPolicyError(
                f"HexIAM revoke_policy failed ({r.status_code}): {r.text}"
            )

    async def list_tenant_users(
        self,
        *,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        """List users in the tenant from HexIAM."""
        service_token = await self._get_service_token()
        params = f"page={page}&page_size={page_size}"
        if search:
            params += f"&search={quote(search, safe='')}"
        url = f"{self.iam_url}/api/v1/users/?{params}"
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.get(url, headers=self._headers(service_token, tenant_id))
        if r.status_code >= 400:
            raise IAMPolicyError(
                f"HexIAM list_tenant_users failed ({r.status_code}): {r.text}"
            )
        return r.json()


@IAMPolicyFactory.register("hexiam")
def create_hexiam_policy_client(**kwargs) -> IAMPolicyPort:
    kwargs.pop("pool", None)
    return HexIAMPolicyClient(**kwargs)

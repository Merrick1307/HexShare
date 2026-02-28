from __future__ import annotations

import os
from typing import Any, Mapping, Optional

import httpx

from app.infra.factories import AccessControlFactory
from app.ports.access_control import AccessControlPort, AccessDenied, ResourceCtx
from app.ports.authn import Principal


class PDPAccessControl(AccessControlPort):
    def __init__(
        self,
        *,
        iam_url: str,
        client_id: str,
        client_secret: str,
        timeout_s: float = 5.0,
    ) -> None:
        self.iam_url = iam_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_s = timeout_s

    async def authorize(self, *, bearer_token: str, action: str, resource: Optional[ResourceCtx] = None,
                        context: Optional[Mapping[str, Any]] = None) -> Principal:
        """
        Calls HexIAM PDP. HexIAM verifies token + evaluates policy.
        """
        url = f"{self.iam_url}/pdp/decide"

        payload = {
            "token": bearer_token,
            "permission": action,
            "resource": None if resource is None else {
                "type": resource.type,
                "id": resource.id,
                "attrs": dict(resource.attrs or {}),
            },
            "context": dict(context or {}),
        }

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                url,
                json=payload,
                # auth=(self.client_id, self.client_secret),  # Basic auth for the PDP client
            )

        if resp.status_code >= 400:
            raise AccessDenied(f"PDP error: {resp.status_code}")

        data = resp.json()
        if not data.get("allow", False):
            raise AccessDenied(data.get("reason", "forbidden"))

        p = data.get("principal") or {}
        # Normalize principal coming back from HexIAM
        return Principal(
            tenant_id=p.get("tenant_id"),
            user_id=p.get("user_id"),
            client_id=p.get("client_id"),
            token_use=p.get("token_use"),
            subject=p.get("sub"),
            scopes=tuple((p.get("scope") or "").split()),
            roles=(p.get("role"),) if p.get("role") else tuple(),
            issuer=p.get("iss"),
            audience=p.get("aud"),
            issued_at=p.get("iat"),
            expires_at=p.get("exp"),
            policy=p.get("policy") or {},
            jti=p.get("jti"),
            claims=p.get("claims") or p,
        )


def _load_pdp_config():
    iam_url = os.getenv("HEXIAM_URL", "http://localhost:8000")
    client_id = os.getenv("HEXSHARE_CLIENT_ID")
    client_secret = os.getenv("HEXIAM_CLIENT_SECRET")
    timeout_s = float(os.getenv("HEXIAM_PDP_TIMEOUT_S", 5.0))
    return {
        "iam_url": iam_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "timeout_s": timeout_s,
    }

@AccessControlFactory.register("pdp")
def create_pdp_access_control(*, iam_url=None, client_id=None, client_secret=None, **_) -> AccessControlPort:
    config = _load_pdp_config()
    return PDPAccessControl(**config)

import base64
import os
from urllib.parse import urlencode

import httpx

from app.ports.oidc_client import OIDCClientPort, OIDCTokens


class HexIAMOIDCClient(OIDCClientPort):
    def __init__(
        self,
        *,
        iam_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.iam_url = (iam_url or os.getenv("HEXIAM_URL", "")).rstrip("/")
        self.client_id = client_id or os.getenv("HEXSHARE_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("HEXSHARE_CLIENT_SECRET", "")
        self.timeout_s = timeout_s

        if not self.iam_url or not self.client_id:
            raise RuntimeError("Missing HEXIAM_URL or HEXSHARE_CLIENT_ID")

    @property
    def authorize_endpoint(self) -> str:
        return f"{self.iam_url}/api/v1/oidc/authorize"

    @property
    def token_endpoint(self) -> str:
        return f"{self.iam_url}/api/v1/oidc/token"

    @property
    def signup_endpoint(self) -> str:
        return f"{self.iam_url}/api/v1/oidc/signup"

    def build_authorize_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        scope: str,
    ) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    def build_signup_url(self, *, redirect_uri: str) -> str:
        return f"{self.signup_endpoint}?{urlencode({'client_id': self.client_id, 'redirect_uri': redirect_uri})}"

    async def exchange_code(self, *, code: str, redirect_uri: str, code_verifier: str) -> OIDCTokens:
        form = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        headers = {"Accept": "application/json"}

        # client_secret_basic (preferred when you have a secret)
        if self.client_secret:
            basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {basic}"

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.post(self.token_endpoint, data=form, headers=headers)
        r.raise_for_status()
        data = r.json()

        return OIDCTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            id_token=data.get("id_token"),
            expires_in=int(data.get("expires_in") or 3600),
            token_type=data.get("token_type") or "Bearer",
            scope=data.get("scope"),
            raw=data,
        )

    async def refresh(self, *, refresh_token: str) -> OIDCTokens:
        form = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
        }
        headers = {"Accept": "application/json"}
        if self.client_secret:
            basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {basic}"

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.post(self.token_endpoint, data=form, headers=headers)
        r.raise_for_status()
        data = r.json()

        return OIDCTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token") or refresh_token,
            id_token=data.get("id_token"),
            expires_in=int(data.get("expires_in") or 3600),
            token_type=data.get("token_type") or "Bearer",
            scope=data.get("scope"),
            raw=data,
        )
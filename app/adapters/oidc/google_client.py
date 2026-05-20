import os
from typing import Any, Mapping, Optional
from urllib.parse import urlencode

import httpx

from app.infra.factories import OIDCClientFactory
from app.ports.oidc_client import OIDCClientPort, OIDCTokens


class GoogleOIDCClient(OIDCClientPort):
    supports_dedicated_signup = False

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        authorize_url: str | None = None,
        token_url: str | None = None,
        userinfo_url: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.client_id = client_id or os.getenv("GOOGLE_OIDC_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("GOOGLE_OIDC_CLIENT_SECRET", "")
        self.authorize_url = authorize_url or os.getenv(
            "GOOGLE_OIDC_AUTHORIZE_URL",
            "https://accounts.google.com/o/oauth2/v2/auth",
        )
        self.token_url = token_url or os.getenv(
            "GOOGLE_OIDC_TOKEN_URL",
            "https://oauth2.googleapis.com/token",
        )
        self.userinfo_url = userinfo_url or os.getenv(
            "GOOGLE_OIDC_USERINFO_URL",
            "https://openidconnect.googleapis.com/v1/userinfo",
        )
        self.timeout_s = timeout_s

        if not self.client_id or not self.client_secret:
            raise RuntimeError("Missing GOOGLE_OIDC_CLIENT_ID or GOOGLE_OIDC_CLIENT_SECRET")

    def build_authorize_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        scope: str,
        extra_params: Optional[Mapping[str, str]] = None,
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
            "access_type": "offline",
            "include_granted_scopes": "true",
        }
        extras = dict(extra_params or {})
        if extras.pop("screen_hint", None) == "signup":
            extras.setdefault("prompt", "select_account")
        params.update(extras)
        return f"{self.authorize_url}?{urlencode(params)}"

    def build_signup_url(self, *, redirect_uri: str, extra_params: Optional[Mapping[str, str]] = None) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "prompt": "select_account",
        }
        if extra_params:
            params.update(extra_params)
        return f"{self.authorize_url}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str, code_verifier: str) -> OIDCTokens:
        form = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(self.token_url, data=form, headers=headers)
        response.raise_for_status()
        data = response.json()
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
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(self.token_url, data=form, headers=headers)
        response.raise_for_status()
        data = response.json()
        return OIDCTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token") or refresh_token,
            id_token=data.get("id_token"),
            expires_in=int(data.get("expires_in") or 3600),
            token_type=data.get("token_type") or "Bearer",
            scope=data.get("scope"),
            raw=data,
        )

    async def get_user_info(self, *, access_token: str, id_token: Optional[str] = None) -> Mapping[str, Any]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.get(self.userinfo_url, headers=headers)
        response.raise_for_status()
        return response.json()


@OIDCClientFactory.register("google")
def create_google_oidc_client(**kwargs) -> OIDCClientPort:
    return GoogleOIDCClient(**kwargs)

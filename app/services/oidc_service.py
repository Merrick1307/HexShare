import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional, Mapping

from app.ports.oidc_client import OIDCClientPort, OIDCTokens
from app.ports.flow_state import FlowStatePort


@dataclass(frozen=True)
class LoginStart:
    authorize_url: str
    tmp_state_token: str


@dataclass(frozen=True)
class LoginFinish:
    tokens: OIDCTokens
    next_url: str


class OIDCFlowService:
    def __init__(self, oidc: OIDCClientPort, state: FlowStatePort) -> None:
        self.oidc = oidc
        self.state = state

    def _pkce_pair(self) -> tuple[str, str]:
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        return verifier, challenge

    def start_login(self, *, redirect_uri: str, next_url: str, scope: str = "openid profile email") -> LoginStart:
        verifier, challenge = self._pkce_pair()
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)

        tmp = self.state.seal(
            {"state": state, "verifier": verifier, "nonce": nonce, "next": next_url},
            ttl_seconds=600,
        )
        url = self.oidc.build_authorize_url(
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=challenge,
            scope=scope,
        )
        return LoginStart(authorize_url=url, tmp_state_token=tmp)

    async def finish_login(self, *, redirect_uri: str, code: str, state: str, tmp_state_token: str) -> LoginFinish:
        tmp = self.state.unseal(tmp_state_token)
        if tmp.get("state") != state:
            raise ValueError("state mismatch")

        tokens = await self.oidc.exchange_code(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=tmp["verifier"],
        )
        return LoginFinish(tokens=tokens, next_url=tmp.get("next") or "/")

    def start_signup(
        self,
        *,
        redirect_uri: str,
        next_url: str,
        scope: str = "openid profile email",
        extra_params: Optional[Mapping[str, str]] = None,
    ) -> LoginStart:
        # Same as start_login but adds signup hints
        verifier, challenge = self._pkce_pair()
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)

        tmp = self.state.seal(
            {"state": state, "verifier": verifier, "nonce": nonce, "next": next_url},
            ttl_seconds=600,
        )

        url = self.oidc.build_authorize_url(
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=challenge,
            scope=scope,
            extra_params=extra_params or {"screen_hint": "signup"},
        )
        return LoginStart(authorize_url=url, tmp_state_token=tmp)

    def signup_start(
        self,
        *,
        redirect_uri: str,
        next_url: str,
        scope: str = "openid profile email",
        extra_params: Optional[Mapping[str, str]] = None,
    ):
        # one entrypoint:
        if getattr(self.oidc, "supports_dedicated_signup", False):
            # dedicated signup page: no PKCE, no tmp cookie, no callback assumed
            url = self.oidc.build_signup_url(redirect_uri=redirect_uri, extra_params=extra_params)
            return {"mode": "dedicated", "url": url}

        # otherwise: signup-via-authorize (needs tmp cookie + callback)
        start = self.start_signup(
            redirect_uri=redirect_uri,
            next_url=next_url,
            scope=scope,
            extra_params=extra_params,
        )
        return {"mode": "oidc", "authorize_url": start.authorize_url, "tmp": start.tmp_state_token}
import os
from typing import Any

import jwt

from app.infra.factories import AuthenticatorFactory
from app.ports.authn import AuthenticatorPort, Principal


class LocalJWTAuthenticator(AuthenticatorPort):
    def __init__(
        self,
        *,
        jwt_secret: str | None = None,
        expected_aud: str | None = None,
    ) -> None:
        self.jwt_secret = jwt_secret or os.getenv("HEXSHARE_JWT_SECRET")
        self.expected_aud = expected_aud or os.getenv("HEXSHARE_AUTH_AUDIENCE", "hexshare")
        if not self.jwt_secret:
            raise RuntimeError("Missing HEXSHARE_JWT_SECRET for local auth")

    def authenticate(self, bearer_token: str) -> Principal:
        token_payload: dict[str, Any] = self._decode_token(bearer_token)
        token_use = token_payload.get("token_use")
        if token_use not in (None, "access"):
            raise jwt.InvalidTokenError("invalid token_use")

        scopes = token_payload.get("scope") or ""
        roles = tuple(token_payload.get("roles") or ())
        return Principal(
            tenant_id=token_payload.get("tenant_id"),
            user_id=token_payload.get("user_id"),
            client_id=token_payload.get("client_id"),
            token_use=token_use,
            subject=token_payload.get("sub"),
            scopes=tuple(str(scopes).split()),
            roles=roles,
            issuer=token_payload.get("iss"),
            audience=token_payload.get("aud"),
            issued_at=token_payload.get("iat"),
            expires_at=token_payload.get("exp"),
            policy=token_payload.get("policy") or {},
            jti=token_payload.get("jti"),
            claims=token_payload,
        )

    def _decode_token(self, token: str) -> dict[str, Any]:
        options = {
            "require": ["exp", "iat", "sub", "tenant_id", "user_id"],
            "verify_aud": bool(self.expected_aud),
        }
        return jwt.decode(
            token,
            self.jwt_secret,
            algorithms=["HS256"],
            options=options,
            audience=self.expected_aud if self.expected_aud else None,
        )


@AuthenticatorFactory.register("local")
def create_local_authenticator(**kwargs) -> AuthenticatorPort:
    return LocalJWTAuthenticator(**kwargs)

import os
from typing import Any

import jwt

from app.infra.factories import AuthenticatorFactory
from app.ports.authn import AuthenticatorPort, Principal


class HEXIAMAuthenticator(AuthenticatorPort):

    def __init__(
        self,
        *,
        iam_url: str | None = None,
        jwt_secret: str | None = None,
        expected_aud: str | None = None,
        expected_iss_prefix: str | None = None,
    ) -> None:
        self.iam_url = iam_url or os.getenv("HEXIAM_URL", "http://localhost:8000")
        self.jwt_secret = jwt_secret or os.getenv("HEXIAM_JWT_SECRET")  # shared secret
        self.expected_aud = expected_aud or os.getenv("HEXSHARE_CLIENT_ID")
        self.expected_iss_prefix = expected_iss_prefix or os.getenv("HEXIAM_ISS_PREFIX")

        if not self.jwt_secret:
            raise RuntimeError("Missing HEXIAM_JWT_SECRET for HS256 verification")

    async def authenticate(self, bearer_token: str) -> Principal:
        token_payload: dict[str, Any] = self._decode_token(bearer_token)

        scopes_str: str = token_payload.get("scope") or ""
        roles: tuple = (token_payload.get("role"),) if token_payload.get("role") else tuple()
        return Principal(
            tenant_id=token_payload.get("tenant_id"),
            user_id=token_payload.get("user_id"),
            client_id=token_payload.get("client_id"),
            token_use=token_payload.get("token_use"),
            subject=token_payload.get("sub"),
            scopes=tuple(scopes_str.split(" ")),
            roles=roles,
            issuer=token_payload.get("iss"),
            audience=token_payload.get("aud"),
            issued_at=token_payload.get("iat"),
            expires_at=token_payload.get("exp"),
            policy=token_payload.get("policy"),
            jti=token_payload.get("jti"),
            claims=token_payload
        )

    def _decode_token(self, token: str) -> dict[str, Any]:
        options = {"require": ["exp", "iat"], "verify_aud": bool(self.expected_aud)}
        return jwt.decode(
            token, algorithms=["HS256"], options=options, key=self.jwt_secret,
            audience=self.expected_aud
        )


def _load_hexiam_config():
    iam_url = os.getenv("HEXIAM_URL", "http://localhost:8000")
    jwt_secret = os.getenv("HEXIAM_JWT_SECRET")
    expected_aud = os.getenv("HEXSHARE_CLIENT_ID")
    expected_iss_prefix = os.getenv("HEXIAM_ISS_PREFIX")

    return {
        "iam_url": iam_url,
        "jwt_secret": jwt_secret,
        "expected_aud": expected_aud,
        "expected_iss_prefix": expected_iss_prefix
    }

@AuthenticatorFactory.register("hexiam")
def create_hexiam_authenticator(**kwargs) -> AuthenticatorPort:
    config = _load_hexiam_config()
    return HEXIAMAuthenticator(**config)
import json
import logging
import os
import threading
import time
from typing import Any, Optional

import jwt
import urllib.request

from app.infra.factories import AuthenticatorFactory
from app.ports.authn import AuthenticatorPort, Principal

_logger = logging.getLogger(__name__)

ASYMMETRIC_ALGORITHMS = {"ES256", "ES384", "ES512", "RS256", "RS384", "RS512", "PS256", "PS384", "PS512"}


class HEXIAMAuthenticator(AuthenticatorPort):

    def __init__(
        self,
        *,
        iam_url: str | None = None,
        jwt_secret: str | None = None,
        expected_aud: str | None = None,
        expected_iss_prefix: str | None = None,
        jwks_url: str | None = None,
        jwks_cache_ttl_seconds: int = 300,
    ) -> None:
        self.iam_url = iam_url or os.getenv("HEXIAM_URL", "http://localhost:8000")
        self.jwt_secret = jwt_secret or os.getenv("HEXIAM_JWT_SECRET")
        self.expected_aud = expected_aud or os.getenv("HEXSHARE_CLIENT_ID")
        self.expected_iss_prefix = expected_iss_prefix or os.getenv("HEXIAM_ISS_PREFIX")
        self.jwks_url = (jwks_url or os.getenv("HEXIAM_JWKS_URL", "").strip()) or f"{self.iam_url.rstrip('/')}/api/v1/oidc/jwks"
        self.jwks_url = self.jwks_url.replace("localhost", "host.docker.internal")
        self.jwks_cache_ttl_seconds = jwks_cache_ttl_seconds

        self._jwks_lock = threading.RLock()
        self._jwks_keys: dict[str, Any] = {}
        self._jwks_last_fetch: float = 0.0

        has_asymmetric = self._ensure_jwks_loaded()
        if not self.jwt_secret and not has_asymmetric:
            raise RuntimeError(
                "Missing HEXIAM_JWT_SECRET for HS256 and no JWKS keys available for asymmetric verification"
            )

    def authenticate(self, bearer_token: str) -> Principal:
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
            claims=token_payload,
        )

    def _decode_token(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        alg = (header.get("alg") or "HS256").upper()
        kid = header.get("kid")
        options = {"require": ["exp", "iat"], "verify_aud": bool(self.expected_aud)}

        if alg in ASYMMETRIC_ALGORITHMS:
            _logger.debug("Verifying token with %s, kid=%s", alg, kid)
            return self._decode_asymmetric(token, alg, kid, options)

        if alg == "HS256" and self.jwt_secret:
            _logger.debug("Verifying token with HS256 (shared secret)")
            return jwt.decode(
                token,
                algorithms=["HS256"],
                options=options,
                key=self.jwt_secret,
                audience=self.expected_aud,
            )

        raise jwt.InvalidAlgorithmError(
            f"Algorithm {alg} not supported. Configure HEXIAM_JWT_SECRET for HS256 or ensure JWKS is available for asymmetric algorithms."
        )

    def _decode_asymmetric(self, token: str, alg: str, kid: Optional[str], options: dict[str, Any]) -> dict[str, Any]:
        self._ensure_jwks_loaded()

        with self._jwks_lock:
            candidates: list[dict[str, Any]] = []
            if kid and kid in self._jwks_keys:
                candidates = [self._jwks_keys[kid]]
            if not candidates:
                candidates = list(self._jwks_keys.values())

        last_error: Optional[Exception] = None
        for key_data in candidates:
            try:
                return jwt.decode(
                    token,
                    key=key_data["public_key"],
                    algorithms=[alg],
                    options=options,
                    audience=self.expected_aud,
                )
            except jwt.InvalidTokenError as exc:
                last_error = exc

        if last_error:
            raise last_error
        raise jwt.InvalidTokenError("No matching JWKS key found for token verification")

    def _ensure_jwks_loaded(self) -> bool:
        with self._jwks_lock:
            if self._jwks_keys and (time.monotonic() - self._jwks_last_fetch) < self.jwks_cache_ttl_seconds:
                return bool(self._jwks_keys)
            return self._fetch_jwks_locked()

    def _fetch_jwks(self) -> bool:
        with self._jwks_lock:
            return self._fetch_jwks_locked()

    def _fetch_jwks_locked(self) -> bool:
        try:
            req = urllib.request.Request(
                self.jwks_url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            _logger.warning("Failed to fetch JWKS from %s: %s", self.jwks_url, exc)
            return bool(self._jwks_keys)

        keys: dict[str, Any] = {}
        for jwk in raw.get("keys", []):
            kid = jwk.get("kid")
            if not kid:
                continue
            try:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            except Exception:
                try:
                    public_key = jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk))
                except Exception:
                    _logger.warning("Skipping JWK kid=%s: unsupported key type", kid)
                    continue
            keys[kid] = {"public_key": public_key, "alg": jwk.get("alg", "").upper()}

        self._jwks_keys = keys
        self._jwks_last_fetch = time.monotonic()

        _logger.info("Loaded %d JWKS keys from %s", len(keys), self.jwks_url)
        return bool(keys)


def _load_hexiam_config():
    iam_url = os.getenv("HEXIAM_URL", "http://localhost:8000")
    jwt_secret = os.getenv("HEXIAM_JWT_SECRET")
    expected_aud = os.getenv("HEXSHARE_CLIENT_ID")
    expected_iss_prefix = os.getenv("HEXIAM_ISS_PREFIX")
    jwks_url = os.getenv("HEXIAM_JWKS_URL", "").strip() or None

    return {
        "iam_url": iam_url,
        "jwt_secret": jwt_secret,
        "expected_aud": expected_aud,
        "expected_iss_prefix": expected_iss_prefix,
        "jwks_url": jwks_url,
    }

@AuthenticatorFactory.register("hexiam")
def create_hexiam_authenticator(**kwargs) -> AuthenticatorPort:
    config = _load_hexiam_config()
    return HEXIAMAuthenticator(**config)
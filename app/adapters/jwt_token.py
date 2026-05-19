"""
JWT token adapter.

This adapter implements :class:`~app.ports.TokenPort` using PyJWT
for encoding and decoding JSON Web Tokens. Revocations can be backed
by either an in-memory set or Redis, depending on deployment mode.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import jwt  # type: ignore

try:
    from redis import Redis
except ImportError:
    Redis = None  # type: ignore

from app.ports.token_port import TokenPort


class _InMemoryJTIRevocationStore:
    def __init__(self) -> None:
        self._revoked_jtis: Dict[str, datetime] = {}

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def is_revoked(self, jti: str) -> bool:
        now = datetime.now(timezone.utc)
        expired = [key for key, exp in self._revoked_jtis.items() if self._as_utc(exp) <= now]
        for key in expired:
            self._revoked_jtis.pop(key, None)
        return jti in self._revoked_jtis

    def revoke(self, jti: str, expires_at: datetime) -> None:
        self._revoked_jtis[jti] = self._as_utc(expires_at)


class _RedisJTIRevocationStore:
    def __init__(
        self,
        *,
        redis_url: str,
        key_prefix: str = "hexshare:share-token-revoked:",
    ) -> None:
        if Redis is None:
            raise RuntimeError("redis is required for Redis-backed share-token revocation")
        self._redis = Redis.from_url(redis_url, decode_responses=False)
        self._key_prefix = key_prefix

    @staticmethod
    def _ttl_seconds(expires_at: datetime) -> int:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)
        return max(int((expires_at - datetime.now(timezone.utc)).total_seconds()), 0)

    def _key(self, jti: str) -> str:
        return f"{self._key_prefix}{jti}"

    def is_revoked(self, jti: str) -> bool:
        return bool(self._redis.exists(self._key(jti)))

    def revoke(self, jti: str, expires_at: datetime) -> None:
        ttl_seconds = self._ttl_seconds(expires_at)
        key = self._key(jti)
        if ttl_seconds <= 0:
            self._redis.delete(key)
            return
        self._redis.set(key, b"1", ex=ttl_seconds)


class JWTTokenAdapter(TokenPort):
    """PyJWT implementation of the token port."""

    def __init__(
        self,
        secret: str | None = None,
        *,
        revocation_store: str | None = None,
        redis_url: str | None = None,
        revocation_key_prefix: str | None = None,
    ) -> None:
        self._secret = secret or os.environ.get("HEXSHARE_JWT_SECRET", uuid.uuid4().hex)

        backend = (revocation_store or os.getenv("HEXSHARE_SHARE_TOKEN_REVOCATION_STORE", "memory")).strip().lower()
        if backend in {"memory", "inmemory"}:
            self._revocation_store = _InMemoryJTIRevocationStore()
        elif backend == "redis":
            resolved_redis_url = redis_url or os.getenv("REDIS_URL")
            if not resolved_redis_url:
                raise RuntimeError("REDIS_URL is required for Redis-backed share-token revocation")
            key_prefix = revocation_key_prefix or os.getenv(
                "HEXSHARE_SHARE_TOKEN_REVOCATION_PREFIX",
                "hexshare:share-token-revoked:",
            )
            self._revocation_store = _RedisJTIRevocationStore(
                redis_url=resolved_redis_url,
                key_prefix=key_prefix,
            )
        else:
            raise RuntimeError(f"Unsupported share-token revocation store: {backend}")

    def generate_jti(self) -> str:
        return uuid.uuid4().hex

    def encode_share_token(
        self,
        *,
        tenant_id: str,
        document_id: str,
        link_id: str,
        jti: str,
        expires_at: datetime,
        permissions: Dict[str, bool],
        require_email: bool,
    ) -> str:
        payload = {
            "sub": document_id,
            "tid": tenant_id,
            "lid": link_id,
            "jti": jti,
            "exp": int(expires_at.replace(tzinfo=timezone.utc).timestamp()),
            "perms": permissions,
            "require_email": require_email,
        }
        token = jwt.encode(payload, self._secret, algorithm="HS256")
        return token

    def decode_share_token(self, token: str) -> Dict[str, Any]:
        payload = jwt.decode(token, self._secret, algorithms=["HS256"])
        jti: str = payload.get("jti")
        if jti and self._revocation_store.is_revoked(jti):
            raise jwt.InvalidTokenError("Token has been revoked")
        return payload

    async def revoke_jti(self, jti: str, expires_at: datetime) -> None:
        self._revocation_store.revoke(jti, expires_at)

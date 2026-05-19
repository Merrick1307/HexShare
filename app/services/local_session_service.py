from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

import jwt


@dataclass(frozen=True)
class LocalSessionTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int
    token_type: str = "Bearer"


class LocalSessionService:
    def __init__(
        self,
        *,
        pool,
        jwt_secret: str | None = None,
        tenant_id: str | None = None,
        issuer: str | None = None,
        audience: str | None = None,
        access_ttl_seconds: int | None = None,
        refresh_ttl_seconds: int | None = None,
    ) -> None:
        self._pool = pool
        self._jwt_secret = jwt_secret or os.getenv("HEXSHARE_JWT_SECRET")
        self._tenant_id = tenant_id or os.getenv("HEXSHARE_LOCAL_TENANT_ID", "local")
        public_url = (os.getenv("HEXSHARE_PUBLIC_URL") or "http://localhost:8099").rstrip("/")
        self._issuer = issuer or public_url
        self._audience = audience or os.getenv("HEXSHARE_AUTH_AUDIENCE", "hexshare")
        self._access_ttl_seconds = int(os.getenv("HEXSHARE_LOCAL_ACCESS_TTL_SECONDS", access_ttl_seconds or 900))
        self._refresh_ttl_seconds = int(os.getenv("HEXSHARE_LOCAL_REFRESH_TTL_SECONDS", refresh_ttl_seconds or 60 * 60 * 24 * 30))
        if not self._jwt_secret:
            raise RuntimeError("Missing HEXSHARE_JWT_SECRET for local session service")

    async def issue_session_from_user_info(self, *, idp: str, user_info: Mapping[str, Any]) -> LocalSessionTokens:
        identity = self._identity_from_user_info(user_info)
        await self._upsert_local_user(
            user_id=identity["user_id"],
            email=identity["email"],
            name=identity["name"],
            auth_provider=idp,
            provider_subject=identity["subject"],
        )
        policy = await self._build_policy_map(user_id=identity["user_id"])
        return self._issue_tokens(
            user_id=identity["user_id"],
            subject=identity["subject"],
            email=identity["email"],
            name=identity["name"],
            idp=idp,
            policy=policy,
        )

    async def refresh_session(self, *, refresh_token: str) -> LocalSessionTokens:
        payload = self._decode_token(refresh_token, expected_token_use="refresh")
        user_id = str(payload.get("user_id") or "").strip()
        subject = str(payload.get("sub") or user_id).strip()
        if not user_id or not subject:
            raise ValueError("invalid_refresh_token")
        policy = await self._build_policy_map(user_id=user_id)
        return self._issue_tokens(
            user_id=user_id,
            subject=subject,
            email=payload.get("email"),
            name=payload.get("name"),
            idp=str(payload.get("idp") or "local"),
            policy=policy,
        )

    def _issue_tokens(
        self,
        *,
        user_id: str,
        subject: str,
        email: Optional[str],
        name: Optional[str],
        idp: str,
        policy: Mapping[str, int],
    ) -> LocalSessionTokens:
        access_token = self._encode_token(
            token_use="access",
            user_id=user_id,
            subject=subject,
            email=email,
            name=name,
            idp=idp,
            ttl_seconds=self._access_ttl_seconds,
            policy=policy,
        )
        refresh_token = self._encode_token(
            token_use="refresh",
            user_id=user_id,
            subject=subject,
            email=email,
            name=name,
            idp=idp,
            ttl_seconds=self._refresh_ttl_seconds,
            policy={},
        )
        return LocalSessionTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._access_ttl_seconds,
            refresh_expires_in=self._refresh_ttl_seconds,
        )

    def _encode_token(
        self,
        *,
        token_use: str,
        user_id: str,
        subject: str,
        email: Optional[str],
        name: Optional[str],
        idp: str,
        ttl_seconds: int,
        policy: Mapping[str, int],
    ) -> str:
        now = datetime.now(timezone.utc)
        exp = now + timedelta(seconds=ttl_seconds)
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": subject,
            "tenant_id": self._tenant_id,
            "user_id": user_id,
            "client_id": "hexshare-local",
            "token_use": token_use,
            "roles": ["user"],
            "policy": dict(policy),
            "scope": "openid profile email",
            "email": email,
            "name": name,
            "idp": idp,
            "jti": uuid.uuid4().hex,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        return jwt.encode(payload, self._jwt_secret, algorithm="HS256")

    def _decode_token(self, token: str, *, expected_token_use: str) -> dict[str, Any]:
        payload = jwt.decode(
            token,
            self._jwt_secret,
            algorithms=["HS256"],
            audience=self._audience,
            options={"require": ["exp", "iat", "sub", "tenant_id", "user_id"]},
        )
        if payload.get("token_use") != expected_token_use:
            raise ValueError("invalid_token_use")
        return payload

    def _identity_from_user_info(self, user_info: Mapping[str, Any]) -> dict[str, Optional[str]]:
        subject = str(user_info.get("sub") or "").strip()
        email = str(user_info.get("email") or "").strip().lower() or None
        name = str(user_info.get("name") or user_info.get("given_name") or email or subject).strip() or None
        if not subject and not email:
            raise ValueError("oidc_identity_missing_subject")
        user_id = subject or str(email)
        return {
            "subject": subject or user_id,
            "user_id": user_id,
            "email": email,
            "name": name,
        }

    async def _upsert_local_user(
        self,
        *,
        user_id: str,
        email: Optional[str],
        name: Optional[str],
        auth_provider: str,
        provider_subject: str,
    ) -> None:
        sql = """
        INSERT INTO local_users (
            tenant_id,
            user_id,
            email,
            name,
            auth_provider,
            provider_subject,
            created_at,
            last_login_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
        ON CONFLICT (tenant_id, user_id)
        DO UPDATE SET
            email = EXCLUDED.email,
            name = EXCLUDED.name,
            auth_provider = EXCLUDED.auth_provider,
            provider_subject = EXCLUDED.provider_subject,
            last_login_at = NOW()
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                self._tenant_id,
                user_id,
                email,
                name,
                auth_provider,
                provider_subject,
            )

    async def _build_policy_map(self, *, user_id: str) -> dict[str, int]:
        sql = """
        SELECT gm.group_id, gm.permissions
        FROM document_group_memberships gm
        INNER JOIN document_groups dg
            ON dg.tenant_id = gm.tenant_id
           AND dg.id = gm.group_id
        WHERE gm.tenant_id = $1 AND gm.user_id = $2
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, self._tenant_id, user_id)
        return {row["group_id"]: int(row["permissions"] or 0) for row in rows}

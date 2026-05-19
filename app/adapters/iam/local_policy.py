from __future__ import annotations

import os
from typing import Any, Mapping, Optional

import jwt

from app.core.authz import resource_action_map
from app.infra.factories import IAMPolicyFactory
from app.ports.iam_policy import IAMPolicyPort


def _actions_to_bitmask(actions: list[str]) -> int:
    mask = 0
    for action in actions:
        flag = resource_action_map.get(str(action).lower())
        if flag is not None:
            mask |= int(flag)
    return mask


def _granted_by_from_bearer_token(*, bearer_token: str, fallback_user_id: str) -> str:
    secret = os.getenv("HEXSHARE_JWT_SECRET")
    if not secret:
        return fallback_user_id
    try:
        payload = jwt.decode(
            bearer_token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except Exception:
        return fallback_user_id
    actor_user_id = str(payload.get("user_id") or "").strip()
    return actor_user_id or fallback_user_id


class LocalIAMPolicyClient(IAMPolicyPort):
    def __init__(self, *, pool, **_: Any) -> None:
        self._pool = pool

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
        permissions = _actions_to_bitmask(actions)
        granted_by = str((conditions or {}).get("granted_by") or "").strip()
        if not granted_by:
            granted_by = _granted_by_from_bearer_token(
                bearer_token=bearer_token,
                fallback_user_id=user_id,
            )
        sql = """
        INSERT INTO document_group_memberships (
            group_id,
            tenant_id,
            user_id,
            permissions,
            granted_by,
            granted_at
        )
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (group_id, user_id)
        DO UPDATE SET
            permissions = EXCLUDED.permissions,
            granted_by = EXCLUDED.granted_by,
            granted_at = NOW()
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, resource, tenant_id, user_id, permissions, granted_by)

    async def revoke_policy(
        self,
        *,
        bearer_token: str,
        tenant_id: str,
        user_id: str,
        policy_id: str,
    ) -> None:
        sql = """
        DELETE FROM document_group_memberships
        WHERE tenant_id = $1 AND user_id = $2 AND group_id = $3
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, user_id, policy_id)

    async def list_tenant_users(
        self,
        *,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        if not search or not search.strip():
            return {"users": [], "total": 0, "page": page, "page_size": page_size}

        offset = (page - 1) * page_size
        where = "WHERE tenant_id = $1 AND (email ILIKE $2 OR name ILIKE $2 OR user_id ILIKE $2)"
        params: list[Any] = [tenant_id, f"%{search.strip()}%"]

        total_sql = f"SELECT COUNT(*) FROM local_users {where}"
        list_sql = f"""
        SELECT user_id, email, name, auth_provider, created_at, last_login_at
        FROM local_users
        {where}
        ORDER BY last_login_at DESC, created_at DESC
        LIMIT ${len(params) + 1}
        OFFSET ${len(params) + 2}
        """
        params_with_pagination = [*params, page_size, offset]
        async with self._pool.acquire() as con:
            total = await con.fetchval(total_sql, *params)
            rows = await con.fetch(list_sql, *params_with_pagination)
        return {
            "users": [
                {
                    "id": row["user_id"],
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "name": row["name"],
                    "auth_provider": row["auth_provider"],
                }
                for row in rows
            ],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }


@IAMPolicyFactory.register("local")
def create_local_policy_client(**kwargs) -> IAMPolicyPort:
    return LocalIAMPolicyClient(**kwargs)

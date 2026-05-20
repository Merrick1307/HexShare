from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.adapters import jwt_token
from app.adapters.jwt_token import JWTTokenAdapter


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, tuple[bytes, int]] = {}
        self.deleted: list[str] = []

    def exists(self, key: str) -> int:
        return int(key in self.values)

    def set(self, key: str, value: bytes, ex: int) -> None:
        self.values[key] = (value, ex)

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


class FakeRedisModule:
    last_client: FakeRedisClient | None = None

    @classmethod
    def from_url(cls, redis_url: str, decode_responses: bool = False) -> FakeRedisClient:
        assert redis_url == "redis://unit-test"
        assert decode_responses is False
        cls.last_client = FakeRedisClient()
        return cls.last_client


@pytest.mark.asyncio
async def test_memory_revocation_rejects_revoked_token() -> None:
    adapter = JWTTokenAdapter(secret="secret", revocation_store="memory")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = adapter.encode_share_token(
        tenant_id="tenant-1",
        document_id="doc-1",
        link_id="link-1",
        jti="jti-1",
        expires_at=expires_at,
        permissions={"can_download": True},
        require_email=False,
    )

    adapter.decode_share_token(token)
    await adapter.revoke_jti("jti-1", expires_at=expires_at)

    with pytest.raises(Exception):
        adapter.decode_share_token(token)


@pytest.mark.asyncio
async def test_redis_revocation_uses_ttl_key_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_token, "Redis", FakeRedisModule)
    adapter = JWTTokenAdapter(
        secret="secret",
        revocation_store="redis",
        redis_url="redis://unit-test",
        revocation_key_prefix="hexshare:test:",
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    await adapter.revoke_jti("jti-redis", expires_at=expires_at)

    client = FakeRedisModule.last_client
    assert client is not None
    assert "hexshare:test:jti-redis" in client.values
    stored_value, stored_ttl = client.values["hexshare:test:jti-redis"]
    assert stored_value == b"1"
    assert stored_ttl > 0


@pytest.mark.asyncio
async def test_redis_revocation_handles_already_expired_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_token, "Redis", FakeRedisModule)
    adapter = JWTTokenAdapter(
        secret="secret",
        revocation_store="redis",
        redis_url="redis://unit-test",
        revocation_key_prefix="hexshare:test:",
    )
    expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    await adapter.revoke_jti("jti-expired", expires_at=expires_at)

    client = FakeRedisModule.last_client
    assert client is not None
    assert client.deleted == ["hexshare:test:jti-expired"]

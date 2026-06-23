from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.adapters import MemoryStorage, NoopEventBus
from app.domain import ShareLink
from app.ports.token_port import TokenPort
from app.services.link_service import LinkService


class FakeTokenPort(TokenPort):
    def __init__(self) -> None:
        self._counter = 0
        self._revoked: list[tuple[str, datetime]] = []

    def generate_jti(self) -> str:
        self._counter += 1
        return f"jti_{self._counter}"

    def encode_share_token(
        self, *, tenant_id, document_id, link_id, jti, expires_at, permissions, require_email
    ) -> str:
        return f"token:{tenant_id}:{document_id}:{link_id}:{jti}"

    def decode_share_token(self, token: str) -> dict:
        parts = token.split(":")
        return {"tenant_id": parts[1], "document_id": parts[2], "link_id": parts[3], "jti": parts[4]}

    async def revoke_jti(self, jti: str, expires_at: datetime) -> None:
        self._revoked.append((jti, expires_at))


def _make_service() -> tuple[LinkService, MemoryStorage, FakeTokenPort]:
    storage = MemoryStorage()
    token_port = FakeTokenPort()
    event_bus = NoopEventBus()
    service = LinkService(storage=storage, token_port=token_port, event_bus=event_bus)
    return service, storage, token_port


@pytest.mark.asyncio
async def test_create_share_link_persists_and_returns_link():
    service, storage, _ = _make_service()

    link = await service.create_share_link(
        tenant_id="tenant-1",
        document_id="doc-1",
        created_by="user-1",
        expires_in_seconds=3600,
        can_download=True,
        can_print=False,
        require_email=True,
        allowed_emails=["a@b.com"],
    )

    assert link.id.startswith("link_")
    assert link.tenant_id == "tenant-1"
    assert link.document_id == "doc-1"
    assert link.can_download is True
    assert link.can_print is False
    assert link.require_email is True
    assert link.allowed_emails == ["a@b.com"]
    assert link.revoked_at is None
    assert link.jti.startswith("jti_")

    persisted = await storage.get_share_link(tenant_id="tenant-1", link_id=link.id)
    assert persisted is not None
    assert persisted.id == link.id


@pytest.mark.asyncio
async def test_create_share_link_sets_expiry_from_seconds():
    service, _, _ = _make_service()
    before = datetime.utcnow()

    link = await service.create_share_link(
        tenant_id="tenant-1",
        document_id="doc-1",
        created_by="user-1",
        expires_in_seconds=7200,
    )

    after = datetime.utcnow()
    assert link.expires_at >= before + timedelta(seconds=7200)
    assert link.expires_at <= after + timedelta(seconds=7200)


@pytest.mark.asyncio
async def test_create_share_link_defaults():
    service, _, _ = _make_service()

    link = await service.create_share_link(
        tenant_id="tenant-1",
        document_id="doc-1",
        created_by="user-1",
        expires_in_seconds=60,
    )

    assert link.can_download is False
    assert link.can_print is False
    assert link.require_email is False
    assert link.allowed_emails == []
    assert link.access_mode.value == "anonymous"
    assert link.bound_email_normalized is None
    assert link.external_access_grant_id is None


@pytest.mark.asyncio
async def test_generate_share_token_returns_encoded_string():
    service, _, _ = _make_service()

    link = await service.create_share_link(
        tenant_id="tenant-1",
        document_id="doc-1",
        created_by="user-1",
        expires_in_seconds=60,
    )

    token = await service.generate_share_token(link)
    assert "tenant-1" in token
    assert "doc-1" in token
    assert link.jti in token



@pytest.mark.asyncio
async def test_revoke_share_link_sets_revoked_at_and_revokes_jti():
    service, storage, token_port = _make_service()

    link = await service.create_share_link(
        tenant_id="tenant-1",
        document_id="doc-1",
        created_by="user-1",
        expires_in_seconds=3600,
    )
    assert link.revoked_at is None

    await service.revoke_share_link(
        tenant_id="tenant-1",
        link_id=link.id,
        revoked_by="admin-1",
    )

    updated = await storage.get_share_link(tenant_id="tenant-1", link_id=link.id)
    assert updated is not None
    assert updated.revoked_at is not None
    assert len(token_port._revoked) == 1
    assert token_port._revoked[0][0] == link.jti


@pytest.mark.asyncio
async def test_create_recipient_share_link_creates_external_party_and_grant():
    service, storage, _ = _make_service()

    link = await service.create_share_link(
        tenant_id="tenant-1",
        document_id="doc-1",
        created_by="user-1",
        expires_in_seconds=3600,
        can_download=True,
        recipient_email="James.Okafor@example.com",
        recipient_display_name="James Okafor",
    )

    assert link.require_email is True
    assert link.allowed_emails == ["james.okafor@example.com"]
    assert link.access_mode.value == "identified"
    assert link.bound_email_normalized == "james.okafor@example.com"
    assert link.external_access_grant_id is not None

    party = await storage.get_external_party_by_email(
        tenant_id="tenant-1",
        email_normalized="james.okafor@example.com",
    )
    assert party is not None
    assert party.display_name == "James Okafor"

    grant = await storage.get_external_access_grant(
        tenant_id="tenant-1",
        grant_id=link.external_access_grant_id,
    )
    assert grant is not None
    assert grant.external_party_id == party.id
    assert grant.resource_type.value == "document"
    assert grant.grant_type.value == "link"
    assert grant.can_download is True


@pytest.mark.asyncio
async def test_revoke_identified_share_link_revokes_external_access_grant():
    service, storage, _ = _make_service()

    link = await service.create_share_link(
        tenant_id="tenant-1",
        document_id="doc-1",
        created_by="user-1",
        expires_in_seconds=3600,
        recipient_email="viewer@example.com",
        recipient_display_name="Viewer",
    )
    assert link.external_access_grant_id is not None

    await service.revoke_share_link(
        tenant_id="tenant-1",
        link_id=link.id,
        revoked_by="user-1",
    )

    grant = await storage.get_external_access_grant(
        tenant_id="tenant-1",
        grant_id=link.external_access_grant_id,
    )
    assert grant is not None
    assert grant.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_nonexistent_link_is_noop():
    service, _, token_port = _make_service()

    await service.revoke_share_link(
        tenant_id="tenant-1",
        link_id="link_does_not_exist",
        revoked_by="admin-1",
    )

    assert len(token_port._revoked) == 0


@pytest.mark.asyncio
async def test_get_share_link_returns_existing():
    service, _, _ = _make_service()

    created = await service.create_share_link(
        tenant_id="tenant-1",
        document_id="doc-1",
        created_by="user-1",
        expires_in_seconds=60,
    )

    fetched = await service.get_share_link(tenant_id="tenant-1", link_id=created.id)
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_share_link_returns_none_for_missing():
    service, _, _ = _make_service()

    result = await service.get_share_link(tenant_id="tenant-1", link_id="nope")
    assert result is None


@pytest.mark.asyncio
async def test_list_share_links_filters_by_document():
    service, _, _ = _make_service()

    await service.create_share_link(tenant_id="t1", document_id="doc-1", created_by="u1", expires_in_seconds=60)
    await service.create_share_link(tenant_id="t1", document_id="doc-2", created_by="u1", expires_in_seconds=60)
    await service.create_share_link(tenant_id="t1", document_id="doc-1", created_by="u1", expires_in_seconds=60)

    all_links = list(await service.list_share_links(tenant_id="t1"))
    assert len(all_links) == 3

    doc1_links = list(await service.list_share_links(tenant_id="t1", document_id="doc-1"))
    assert len(doc1_links) == 2
    assert all(link.document_id == "doc-1" for link in doc1_links)

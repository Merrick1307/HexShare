from __future__ import annotations

from datetime import datetime

import pytest

from app.adapters import MemoryStorage
from app.auth.tenant_auth import TenantPrincipal
from app.domain import DocumentGroup
from app.services.external_room_access_service import ExternalRoomAccessService


def _principal() -> TenantPrincipal:
    return TenantPrincipal(
        tenant_id="tenant-1",
        user_id="user-1",
        token="fake-token",
        policy={},
    )


async def _seed_group(storage: MemoryStorage, group_id: str = "dcgrp_room1") -> DocumentGroup:
    group = DocumentGroup(
        id=group_id,
        tenant_id="tenant-1",
        name="Data Room",
        description="Due diligence",
        created_by="user-1",
        created_at=datetime.utcnow(),
    )
    await storage.save_document_group(group)
    return group


@pytest.mark.asyncio
async def test_provision_room_access_creates_party_grant_and_invite():
    storage = MemoryStorage()
    await _seed_group(storage)
    service = ExternalRoomAccessService(storage=storage, jwt_secret="test-secret")

    provisioned = await service.provision_room_access(
        principal=_principal(),
        room_id="dcgrp_room1",
        recipient_email="james@example.com",
        recipient_display_name="James Okafor",
        can_download=True,
    )

    assert provisioned.party.display_name == "James Okafor"
    assert provisioned.grant.resource_type.value == "room"
    assert provisioned.grant.grant_type.value == "provisioned"
    assert provisioned.grant.can_download is True
    assert provisioned.grant.permissions > 0
    assert provisioned.invite_token

    party = await storage.get_external_party_by_email(
        tenant_id="tenant-1",
        email_normalized="james@example.com",
    )
    assert party is not None
    assert party.id == provisioned.party.id


@pytest.mark.asyncio
async def test_create_session_from_invite_binds_room_scoped_principal():
    storage = MemoryStorage()
    await _seed_group(storage)
    service = ExternalRoomAccessService(storage=storage, jwt_secret="test-secret")

    provisioned = await service.provision_room_access(
        principal=_principal(),
        room_id="dcgrp_room1",
        recipient_email="viewer@example.com",
        recipient_display_name="Viewer",
        can_download=True,
    )

    tokens = await service.create_session_from_invite(
        invite_token=provisioned.invite_token,
        email="viewer@example.com",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )

    principal = await service.authenticate_access_token(access_token=tokens.access_token)

    assert principal.tenant_id == "tenant-1"
    assert principal.room_id == "dcgrp_room1"
    assert principal.external_party_id == provisioned.party.id
    assert principal.email == "viewer@example.com"
    assert principal.permissions == provisioned.grant.permissions


@pytest.mark.asyncio
async def test_revoked_room_grant_blocks_existing_access_token():
    storage = MemoryStorage()
    await _seed_group(storage)
    service = ExternalRoomAccessService(storage=storage, jwt_secret="test-secret")

    provisioned = await service.provision_room_access(
        principal=_principal(),
        room_id="dcgrp_room1",
        recipient_email="viewer@example.com",
        recipient_display_name="Viewer",
        can_download=False,
    )
    tokens = await service.create_session_from_invite(
        invite_token=provisioned.invite_token,
        email="viewer@example.com",
        ip_address=None,
        user_agent=None,
    )

    await service.revoke_room_access(
        tenant_id="tenant-1",
        grant_id=provisioned.grant.id,
        room_id="dcgrp_room1",
    )

    with pytest.raises(ValueError, match="grant_revoked"):
        await service.authenticate_access_token(access_token=tokens.access_token)

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

import pytest

from app.adapters import MemoryStorage
from app.auth.tenant_auth import TenantPrincipal
from app.core.authz import DOCUMENT_GROUP_PREFIX, ResourceAction
from app.domain import Document
from app.ports.access_control import AccessDenied
from app.ports.iam_policy import IAMPolicyError, IAMPolicyPort
from app.services.document_group_service import DocumentGroupService


class FakeIAMPolicy(IAMPolicyPort):
    def __init__(self, *, fail_grant: bool = False, fail_revoke: bool = False) -> None:
        self.grants: list[dict] = []
        self.revokes: list[dict] = []
        self._fail_grant = fail_grant
        self._fail_revoke = fail_revoke

    async def grant_policy(
        self, *, bearer_token, tenant_id, user_id, policy_id, resource, actions, conditions=None
    ) -> None:
        if self._fail_grant:
            raise IAMPolicyError("grant failed")
        self.grants.append({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "policy_id": policy_id,
            "resource": resource,
            "actions": actions,
        })

    async def revoke_policy(self, *, bearer_token, tenant_id, user_id, policy_id) -> None:
        if self._fail_revoke:
            raise IAMPolicyError("revoke failed")
        self.revokes.append({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "policy_id": policy_id,
        })


def _make_service(
    *, fail_grant: bool = False, fail_revoke: bool = False
) -> tuple[DocumentGroupService, MemoryStorage, FakeIAMPolicy]:
    storage = MemoryStorage()
    iam = FakeIAMPolicy(fail_grant=fail_grant, fail_revoke=fail_revoke)
    service = DocumentGroupService(storage=storage, iam_policy=iam)
    return service, storage, iam


def _owner_bitmask() -> int:
    return int(
        ResourceAction.READ | ResourceAction.WRITE | ResourceAction.DELETE
        | ResourceAction.MANAGE | ResourceAction.EXPORT
    )


def _member_bitmask() -> int:
    return int(ResourceAction.READ | ResourceAction.WRITE | ResourceAction.EXPORT)


def _principal(
    tenant_id: str = "tenant-1",
    user_id: str = "user-1",
    policy: dict | None = None,
    token: str | None = "fake-token",
) -> TenantPrincipal:
    return TenantPrincipal(
        tenant_id=tenant_id,
        user_id=user_id,
        token=token,
        policy=policy or {},
    )


@pytest.mark.asyncio
async def test_create_group_persists_and_returns():
    service, storage, iam = _make_service()
    principal = _principal()

    group = await service.create_group(
        principal=principal,
        name="Engineering",
        description="Eng docs",
    )

    assert group.id.startswith(DOCUMENT_GROUP_PREFIX)
    assert group.name == "Engineering"
    assert group.description == "Eng docs"
    assert group.tenant_id == "tenant-1"
    assert group.created_by == "user-1"

    persisted = await storage.get_document_group(tenant_id="tenant-1", group_id=group.id)
    assert persisted is not None
    assert persisted.name == "Engineering"

    assert len(iam.grants) == 1
    assert iam.grants[0]["resource"] == group.id


@pytest.mark.asyncio
async def test_create_group_requires_bearer_token():
    service, _, _ = _make_service()
    principal = _principal(token=None)

    with pytest.raises(AccessDenied, match="missing_bearer_token"):
        await service.create_group(principal=principal, name="Test")


@pytest.mark.asyncio
async def test_create_group_compensates_on_storage_failure():
    service, storage, iam = _make_service()

    # Sabotage save to raise
    original_save = storage.save_document_group

    async def failing_save(group):
        raise RuntimeError("DB down")

    storage.save_document_group = failing_save
    principal = _principal()

    with pytest.raises(RuntimeError, match="DB down"):
        await service.create_group(principal=principal, name="Broken")

    # IAM grant happened, then compensating revoke
    assert len(iam.grants) == 1
    assert len(iam.revokes) == 1


@pytest.mark.asyncio
async def test_update_group_changes_name():
    service, storage, _ = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Old Name")

    owner_principal = _principal(policy={group.id: _owner_bitmask()})
    updated = await service.update_group(
        principal=owner_principal,
        group_id=group.id,
        name="New Name",
    )

    assert updated.name == "New Name"


@pytest.mark.asyncio
async def test_update_group_denied_without_manage():
    service, _, _ = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="G1")

    reader = _principal(user_id="user-2", policy={group.id: int(ResourceAction.READ)})
    with pytest.raises(AccessDenied, match="insufficient_room_permission"):
        await service.update_group(principal=reader, group_id=group.id, name="Nope")


@pytest.mark.asyncio
async def test_update_nonexistent_group():
    service, _, _ = _make_service()
    principal = _principal(policy={"dcgrp_missing": _owner_bitmask()})

    with pytest.raises(ValueError, match="group_not_found"):
        await service.update_group(principal=principal, group_id="dcgrp_missing", name="X")


@pytest.mark.asyncio
async def test_delete_group_removes_and_transfers_docs():
    service, storage, iam = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Temp")

    # Add a document to the group
    doc = Document(
        id="doc-1", tenant_id="tenant-1", name="file.pdf",
        mime_type="application/pdf", size=100, storage_key="k",
        created_at=datetime.utcnow(), created_by="user-1", room_id=group.id,
    )
    await storage.save_document(doc)

    owner_principal = _principal(policy={group.id: _owner_bitmask()})
    await service.delete_group(principal=owner_principal, group_id=group.id)

    # Group deleted
    assert await storage.get_document_group(tenant_id="tenant-1", group_id=group.id) is None

    # Document still exists but room_id is None
    remaining = await storage.get_document(tenant_id="tenant-1", document_id="doc-1")
    assert remaining is not None
    assert remaining.room_id is None

    # Owner permission granted on orphaned doc
    perm = await storage.get_document_permission(
        tenant_id="tenant-1", document_id="doc-1", user_id="user-1"
    )
    assert perm is not None


@pytest.mark.asyncio
async def test_delete_group_denied_without_manage():
    service, _, _ = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="G")

    reader = _principal(user_id="user-2", policy={group.id: int(ResourceAction.READ)})
    with pytest.raises(AccessDenied, match="insufficient_room_permission"):
        await service.delete_group(principal=reader, group_id=group.id)


@pytest.mark.asyncio
async def test_delete_group_requires_bearer_token():
    service, _, _ = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="G")

    no_token = _principal(token=None, policy={group.id: _owner_bitmask()})
    with pytest.raises(AccessDenied, match="missing_bearer_token"):
        await service.delete_group(principal=no_token, group_id=group.id)


@pytest.mark.asyncio
async def test_add_member_grants_policy():
    service, storage, iam = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Team")

    owner_principal = _principal(policy={group.id: _owner_bitmask()})
    await service.add_member(
        principal=owner_principal,
        group_id=group.id,
        member_user_id="user-2",
        role="member",
    )

    # The initial grant + the member grant
    assert len(iam.grants) == 2
    member_grant = iam.grants[1]
    assert member_grant["user_id"] == "user-2"


@pytest.mark.asyncio
async def test_add_member_owner_role():
    service, _, iam = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Team")

    owner_principal = _principal(policy={group.id: _owner_bitmask()})
    await service.add_member(
        principal=owner_principal,
        group_id=group.id,
        member_user_id="user-2",
        role="owner",
    )

    member_grant = iam.grants[1]
    assert "manage" in member_grant["actions"]


@pytest.mark.asyncio
async def test_add_member_denied_without_manage():
    service, _, _ = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Team")

    reader = _principal(user_id="user-2", policy={group.id: int(ResourceAction.READ)})
    with pytest.raises(AccessDenied, match="insufficient_room_permission"):
        await service.add_member(
            principal=reader,
            group_id=group.id,
            member_user_id="user-3",
        )


@pytest.mark.asyncio
async def test_remove_member_revokes_policy():
    service, _, iam = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Team")

    owner_principal = _principal(policy={group.id: _owner_bitmask()})
    await service.add_member(
        principal=owner_principal, group_id=group.id, member_user_id="user-2",
    )

    await service.remove_member(
        principal=owner_principal, group_id=group.id, member_user_id="user-2",
    )

    assert len(iam.revokes) == 1
    assert iam.revokes[0]["user_id"] == "user-2"


@pytest.mark.asyncio
async def test_remove_creator_denied():
    service, _, _ = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Team")

    owner_principal = _principal(policy={group.id: _owner_bitmask()})
    with pytest.raises(AccessDenied, match="cannot_remove_creator"):
        await service.remove_member(
            principal=owner_principal,
            group_id=group.id,
            member_user_id="user-1",  # creator
        )


@pytest.mark.asyncio
async def test_list_user_groups_returns_only_policy_groups():
    service, storage, _ = _make_service()
    principal = _principal()

    g1 = await service.create_group(principal=principal, name="G1")
    g2 = await service.create_group(principal=principal, name="G2")

    viewer = _principal(user_id="user-2", policy={g1.id: int(ResourceAction.READ)})
    groups = list(await service.list_user_groups(principal=viewer))
    assert len(groups) == 1
    assert groups[0].id == g1.id


@pytest.mark.asyncio
async def test_get_group_enforces_read_permission():
    service, _, _ = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Private")

    no_access = _principal(user_id="user-2", policy={})
    with pytest.raises(AccessDenied, match="insufficient_room_permission"):
        await service.get_group(principal=no_access, group_id=group.id)


@pytest.mark.asyncio
async def test_list_group_documents():
    service, storage, _ = _make_service()
    principal = _principal()

    group = await service.create_group(principal=principal, name="Team")

    doc = Document(
        id="doc-1", tenant_id="tenant-1", name="file.pdf",
        mime_type="application/pdf", size=100, storage_key="k",
        created_at=datetime.utcnow(), created_by="user-1", room_id=group.id,
    )
    await storage.save_document(doc)

    reader = _principal(policy={group.id: int(ResourceAction.READ)})
    docs = list(await service.list_group_documents(principal=reader, group_id=group.id))
    assert len(docs) == 1
    assert docs[0].id == "doc-1"

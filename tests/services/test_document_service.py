from __future__ import annotations

from datetime import datetime

import pytest

from app.adapters import MemoryStorage, NoopEventBus
from app.auth.tenant_auth import TenantPrincipal
from app.core.authz import ResourceAction
from app.domain import Document, DocumentPermission
from app.ports.access_control import AccessDenied
from app.services.document_service import DocumentService


def _make_service() -> tuple[DocumentService, MemoryStorage]:
    storage = MemoryStorage()
    event_bus = NoopEventBus()
    service = DocumentService(storage=storage, event_bus=event_bus)
    return service, storage


def _principal(
    tenant_id: str = "tenant-1",
    user_id: str = "user-1",
    policy: dict | None = None,
) -> TenantPrincipal:
    return TenantPrincipal(
        tenant_id=tenant_id,
        user_id=user_id,
        token="fake-token",
        policy=policy or {},
    )


@pytest.mark.asyncio
async def test_create_document_persists_and_returns():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=1024,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    assert doc.id.startswith("doc_")
    assert doc.tenant_id == "tenant-1"
    assert doc.name == "report.pdf"
    assert doc.size == 1024
    assert doc.room_id is None

    persisted = await storage.get_document(tenant_id="tenant-1", document_id=doc.id)
    assert persisted is not None


@pytest.mark.asyncio
async def test_create_ungrouped_document_grants_owner_permission():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=1024,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    perm = await storage.get_document_permission(
        tenant_id="tenant-1", document_id=doc.id, user_id="user-1"
    )
    assert perm is not None
    assert perm.permissions & int(ResourceAction.READ)
    assert perm.permissions & int(ResourceAction.WRITE)
    assert perm.permissions & int(ResourceAction.DELETE)
    assert perm.permissions & int(ResourceAction.MANAGE)
    assert perm.permissions & int(ResourceAction.EXPORT)


@pytest.mark.asyncio
async def test_create_grouped_document_does_not_create_permission():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=1024,
        storage_key="docs/report.pdf",
        created_by="user-1",
        room_id="dcgrp_abc",
    )

    assert doc.room_id == "dcgrp_abc"
    perm = await storage.get_document_permission(
        tenant_id="tenant-1", document_id=doc.id, user_id="user-1"
    )
    assert perm is None


@pytest.mark.asyncio
async def test_create_document_with_explicit_id():
    service, _ = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
        document_id="doc_custom_id",
    )

    assert doc.id == "doc_custom_id"



@pytest.mark.asyncio
async def test_require_access_ungrouped_allowed():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    principal = _principal()
    result = await service.require_document_access(
        principal=principal,
        document_id=doc.id,
        required=ResourceAction.READ,
    )
    assert result.id == doc.id


@pytest.mark.asyncio
async def test_require_access_ungrouped_denied_for_other_user():
    service, _ = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    other = _principal(user_id="user-2")
    with pytest.raises(AccessDenied, match="insufficient_document_permission"):
        await service.require_document_access(
            principal=other,
            document_id=doc.id,
            required=ResourceAction.READ,
        )


@pytest.mark.asyncio
async def test_require_access_grouped_allowed_via_policy():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
        room_id="dcgrp_room1",
    )

    principal = _principal(policy={"dcgrp_room1": int(ResourceAction.READ | ResourceAction.WRITE)})
    result = await service.require_document_access(
        principal=principal,
        document_id=doc.id,
        required=ResourceAction.READ,
    )
    assert result.id == doc.id


@pytest.mark.asyncio
async def test_require_access_grouped_denied_without_policy():
    service, _ = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
        room_id="dcgrp_room1",
    )

    principal = _principal(policy={})
    with pytest.raises(AccessDenied, match="insufficient_room_permission"):
        await service.require_document_access(
            principal=principal,
            document_id=doc.id,
            required=ResourceAction.READ,
        )


@pytest.mark.asyncio
async def test_require_access_nonexistent_document():
    service, _ = _make_service()
    principal = _principal()

    with pytest.raises(ValueError, match="document_not_found"):
        await service.require_document_access(
            principal=principal,
            document_id="doc_missing",
            required=ResourceAction.READ,
        )


@pytest.mark.asyncio
async def test_delete_document_removes_it():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    principal = _principal()
    await service.delete_document(principal=principal, document_id=doc.id)

    assert await storage.get_document(tenant_id="tenant-1", document_id=doc.id) is None


@pytest.mark.asyncio
async def test_delete_document_denied_without_manage():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    other = _principal(user_id="user-2")
    with pytest.raises(AccessDenied):
        await service.delete_document(principal=other, document_id=doc.id)



@pytest.mark.asyncio
async def test_move_document_to_group():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    principal = _principal(policy={"dcgrp_target": int(ResourceAction.WRITE)})
    moved = await service.move_document_to_group(
        principal=principal,
        document_id=doc.id,
        group_id="dcgrp_target",
    )

    assert moved.room_id == "dcgrp_target"


@pytest.mark.asyncio
async def test_move_document_to_group_denied_without_target_write():
    service, _ = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    principal = _principal(policy={})
    with pytest.raises(AccessDenied, match="insufficient_target_group_permission"):
        await service.move_document_to_group(
            principal=principal,
            document_id=doc.id,
            group_id="dcgrp_target",
        )


@pytest.mark.asyncio
async def test_remove_document_from_group():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
        room_id="dcgrp_room1",
    )

    principal = _principal(policy={"dcgrp_room1": int(ResourceAction.READ | ResourceAction.MANAGE)})
    moved = await service.move_document_to_group(
        principal=principal,
        document_id=doc.id,
        group_id=None,
    )

    assert moved.room_id is None



@pytest.mark.asyncio
async def test_grant_and_revoke_document_permission():
    service, storage = _make_service()

    doc = await service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=512,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )

    perm = await service.grant_document_permission(
        tenant_id="tenant-1",
        document_id=doc.id,
        user_id="user-2",
        permissions=int(ResourceAction.READ),
        granted_by="user-1",
    )
    assert perm.user_id == "user-2"
    assert perm.permissions & int(ResourceAction.READ)

    fetched = await storage.get_document_permission(
        tenant_id="tenant-1", document_id=doc.id, user_id="user-2"
    )
    assert fetched is not None

    await service.revoke_document_permission(
        tenant_id="tenant-1", document_id=doc.id, user_id="user-2"
    )
    fetched = await storage.get_document_permission(
        tenant_id="tenant-1", document_id=doc.id, user_id="user-2"
    )
    assert fetched is None



@pytest.mark.asyncio
async def test_list_accessible_documents_only_returns_permitted():
    service, storage = _make_service()

    await service.create_document(
        tenant_id="tenant-1", name="a.pdf", mime_type="application/pdf",
        size=100, storage_key="a", created_by="user-1",
    )
    await service.create_document(
        tenant_id="tenant-1", name="b.pdf", mime_type="application/pdf",
        size=100, storage_key="b", created_by="user-2",
    )

    principal = _principal(user_id="user-1")
    docs = list(await service.list_accessible_documents(principal=principal))
    assert len(docs) == 1
    assert docs[0].name == "a.pdf"

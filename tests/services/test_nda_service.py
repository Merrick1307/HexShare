from __future__ import annotations

from datetime import datetime

import pytest

from app.adapters import MemoryStorage
from app.core.authz import ResourceAction
from app.domain import Document, DocumentGroup, NdaContentType, NdaScopeType, NdaSubjectKind
from app.ports.object_storage_port import ObjectDescriptor, ObjectStoragePort, ObjectWriteRequest, TemporaryObjectAccess
from app.ports.rendered_page_cache_port import RenderedPageCachePort
from app.services import (
    DocumentProcessor,
    DocumentService,
    ExternalRoomPrincipal,
    ExternalRoomViewerService,
    NdaAcceptanceRequired,
    NdaError,
    NdaService,
    NdaSubject,
    ProcessedDocument,
    ProcessingContext,
    RenderedPage,
    ViewPolicy,
)


class _ObjectStorage(ObjectStoragePort):
    """Minimal in-memory object storage for NDA content."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def build_object_key(self, *, tenant_id: str, document_id: str, filename: str) -> str:
        return f"{tenant_id}/{document_id}/{filename}"

    async def read_object(self, *, object_key: str) -> bytes:
        return self.objects.get(object_key, b"source-bytes")

    async def write_object(self, request: ObjectWriteRequest) -> ObjectDescriptor:
        self.objects[request.object_key] = request.content
        return ObjectDescriptor(object_key=request.object_key, size=len(request.content))

    async def create_temporary_upload(self, *, object_key: str, content_type: str, expires_in: int = 900) -> TemporaryObjectAccess:
        return TemporaryObjectAccess(object_key=object_key, url="https://upload.test")

    async def create_temporary_download(self, *, object_key: str, expires_in: int = 900, filename: str | None = None) -> TemporaryObjectAccess:
        return TemporaryObjectAccess(object_key=object_key, url="https://download.test", method="GET")

    async def head_object(self, *, object_key: str) -> ObjectDescriptor | None:
        return None

    async def delete_object(self, *, object_key: str) -> None:
        self.objects.pop(object_key, None)


def _party_subject(party_id: str = "ep_1") -> NdaSubject:
    return NdaSubject(
        subject_kind=NdaSubjectKind.EXTERNAL_PARTY,
        subject_id=party_id,
        external_party_id=party_id,
        presented_email="viewer@example.com",
        session_id="ers_1",
    )


async def _make_document(storage: MemoryStorage, *, doc_id: str, room_id: str | None) -> Document:
    if room_id:
        await storage.save_document_group(
            DocumentGroup(
                id=room_id, tenant_id="tenant-1", name="Room", description=None,
                created_by="user-1", created_at=datetime.utcnow(),
            )
        )
    document = Document(
        id=doc_id, tenant_id="tenant-1", name="report.pdf", mime_type="application/pdf",
        size=10, storage_key=f"documents/{doc_id}/report.pdf", created_at=datetime.utcnow(),
        created_by="user-1", room_id=room_id,
    )
    await storage.save_document(document)
    return document


def _service(storage: MemoryStorage) -> NdaService:
    return NdaService(storage=storage, object_storage=_ObjectStorage())


# -- policy lifecycle & versioning ---------------------------------------------------

@pytest.mark.asyncio
async def test_set_policy_creates_v1_and_mirrors_text_to_object_storage():
    storage = MemoryStorage()
    obj = _ObjectStorage()
    service = NdaService(storage=storage, object_storage=obj)

    policy = await service.set_policy(
        tenant_id="tenant-1", scope_type=NdaScopeType.ROOM, scope_id="dcgrp_1",
        created_by="user-1", content_type=NdaContentType.TEXT, text_body="Please sign.", title="Room NDA",
    )

    assert policy.version == 1
    assert policy.text_body == "Please sign."
    assert policy.text_storage_key in obj.objects
    assert obj.objects[policy.text_storage_key] == b"Please sign."


@pytest.mark.asyncio
async def test_set_policy_bumps_version_only_when_content_changes():
    storage = MemoryStorage()
    service = _service(storage)
    common = dict(tenant_id="tenant-1", scope_type=NdaScopeType.ROOM, scope_id="dcgrp_1", created_by="user-1", content_type=NdaContentType.TEXT)

    v1 = await service.set_policy(**common, text_body="Original")
    same = await service.set_policy(**common, text_body="Original")
    changed = await service.set_policy(**common, text_body="Revised")

    assert v1.version == 1
    assert same.version == 1  # unchanged content keeps the version
    assert changed.version == 2  # changed content bumps → forces re-acceptance


@pytest.mark.asyncio
async def test_text_policy_requires_text_and_pdf_requires_bytes():
    storage = MemoryStorage()
    service = _service(storage)
    with pytest.raises(NdaError):
        await service.set_policy(
            tenant_id="tenant-1", scope_type=NdaScopeType.DOCUMENT, scope_id="doc_1",
            created_by="u", content_type=NdaContentType.TEXT, text_body="   ",
        )
    with pytest.raises(NdaError):
        await service.set_policy(
            tenant_id="tenant-1", scope_type=NdaScopeType.DOCUMENT, scope_id="doc_1",
            created_by="u", content_type=NdaContentType.PDF, pdf_bytes=None,
        )


# -- applicable / outstanding / require --------------------------------------------

@pytest.mark.asyncio
async def test_applicable_policies_include_room_and_document():
    storage = MemoryStorage()
    service = _service(storage)
    document = await _make_document(storage, doc_id="doc_1", room_id="dcgrp_1")
    await service.set_policy(tenant_id="tenant-1", scope_type=NdaScopeType.ROOM, scope_id="dcgrp_1", created_by="u", content_type=NdaContentType.TEXT, text_body="room")
    await service.set_policy(tenant_id="tenant-1", scope_type=NdaScopeType.DOCUMENT, scope_id="doc_1", created_by="u", content_type=NdaContentType.TEXT, text_body="doc")

    policies = await service.applicable_policies(document=document)
    scopes = {(p.scope_type.value, p.scope_id) for p in policies}
    assert scopes == {("room", "dcgrp_1"), ("document", "doc_1")}


@pytest.mark.asyncio
async def test_require_all_accepted_blocks_until_every_policy_accepted():
    storage = MemoryStorage()
    service = _service(storage)
    document = await _make_document(storage, doc_id="doc_1", room_id="dcgrp_1")
    room = await service.set_policy(tenant_id="tenant-1", scope_type=NdaScopeType.ROOM, scope_id="dcgrp_1", created_by="u", content_type=NdaContentType.TEXT, text_body="room")
    doc = await service.set_policy(tenant_id="tenant-1", scope_type=NdaScopeType.DOCUMENT, scope_id="doc_1", created_by="u", content_type=NdaContentType.TEXT, text_body="doc")
    subject = _party_subject()

    with pytest.raises(NdaAcceptanceRequired):
        await service.require_all_accepted(document=document, subject=subject)

    # Accept only the room NDA — still blocked by the document NDA.
    await service.accept(policy=room, subject=subject, typed_name="Jane", scroll_confirmed=True, checkbox_confirmed=True)
    with pytest.raises(NdaAcceptanceRequired):
        await service.require_all_accepted(document=document, subject=subject)

    # Accept the document NDA too — now allowed.
    await service.accept(policy=doc, subject=subject, typed_name="Jane", scroll_confirmed=True, checkbox_confirmed=True)
    await service.require_all_accepted(document=document, subject=subject)  # no raise


@pytest.mark.asyncio
async def test_version_bump_reinstates_the_gate():
    storage = MemoryStorage()
    service = _service(storage)
    document = await _make_document(storage, doc_id="doc_1", room_id=None)
    policy = await service.set_policy(tenant_id="tenant-1", scope_type=NdaScopeType.DOCUMENT, scope_id="doc_1", created_by="u", content_type=NdaContentType.TEXT, text_body="v1 text")
    subject = _party_subject()
    await service.accept(policy=policy, subject=subject, typed_name="Jane", scroll_confirmed=True, checkbox_confirmed=True)
    await service.require_all_accepted(document=document, subject=subject)  # accepted

    # New content → v2 → prior acceptance no longer counts.
    await service.set_policy(tenant_id="tenant-1", scope_type=NdaScopeType.DOCUMENT, scope_id="doc_1", created_by="u", content_type=NdaContentType.TEXT, text_body="v2 text")
    with pytest.raises(NdaAcceptanceRequired):
        await service.require_all_accepted(document=document, subject=subject)


@pytest.mark.asyncio
async def test_no_policy_means_no_gate():
    storage = MemoryStorage()
    service = _service(storage)
    document = await _make_document(storage, doc_id="doc_1", room_id=None)
    await service.require_all_accepted(document=document, subject=_party_subject())  # no raise


# -- acceptance validation ----------------------------------------------------------

@pytest.mark.asyncio
async def test_accept_enforces_signature_scroll_and_checkbox():
    storage = MemoryStorage()
    service = _service(storage)
    policy = await service.set_policy(
        tenant_id="tenant-1", scope_type=NdaScopeType.ROOM, scope_id="dcgrp_1", created_by="u",
        content_type=NdaContentType.TEXT, text_body="terms", require_scroll=True, require_typed_signature=True,
    )
    subject = _party_subject()

    with pytest.raises(NdaError):  # missing signature
        await service.accept(policy=policy, subject=subject, typed_name="  ", scroll_confirmed=True, checkbox_confirmed=True)
    with pytest.raises(NdaError):  # not scrolled
        await service.accept(policy=policy, subject=subject, typed_name="Jane", scroll_confirmed=False, checkbox_confirmed=True)
    with pytest.raises(NdaError):  # checkbox not ticked
        await service.accept(policy=policy, subject=subject, typed_name="Jane", scroll_confirmed=True, checkbox_confirmed=False)

    record = await service.accept(policy=policy, subject=subject, typed_name="Jane Doe", scroll_confirmed=True, checkbox_confirmed=True)
    assert record.typed_name == "Jane Doe"
    assert record.nda_version == policy.version
    assert record.subject_kind == NdaSubjectKind.EXTERNAL_PARTY


@pytest.mark.asyncio
async def test_room_policy_status_and_require_room_accepted():
    storage = MemoryStorage()
    service = _service(storage)
    subject = _party_subject()
    # No policy → accepted True, no raise.
    policy, accepted = await service.room_policy_status(tenant_id="tenant-1", room_id="dcgrp_1", subject=subject)
    assert policy is None and accepted is True
    await service.require_room_accepted(tenant_id="tenant-1", room_id="dcgrp_1", subject=subject)

    created = await service.set_policy(tenant_id="tenant-1", scope_type=NdaScopeType.ROOM, scope_id="dcgrp_1", created_by="u", content_type=NdaContentType.TEXT, text_body="terms")
    _, accepted = await service.room_policy_status(tenant_id="tenant-1", room_id="dcgrp_1", subject=subject)
    assert accepted is False
    with pytest.raises(NdaAcceptanceRequired):
        await service.require_room_accepted(tenant_id="tenant-1", room_id="dcgrp_1", subject=subject)
    await service.accept(policy=created, subject=subject, typed_name="Jane", scroll_confirmed=True, checkbox_confirmed=True)
    await service.require_room_accepted(tenant_id="tenant-1", room_id="dcgrp_1", subject=subject)  # no raise


# -- enforcement through the room viewer service -----------------------------------

class _ProcessorStub(DocumentProcessor):
    def __init__(self) -> None:
        super().__init__()

    def describe_view_policy(self, *, filename: str, source_media_type: str | None):
        return ViewPolicy(inline_view_supported=True, view_kind="pdf")

    async def describe_pdf_preview(self, *, content: bytes, cache_key: str | None = None):
        from app.services import PdfPreview
        return PdfPreview(page_count=1)


class _CacheStub(RenderedPageCachePort):
    def __init__(self) -> None:
        self._d: dict[str, object] = {}

    async def get(self, key: str):
        return self._d.get(key)

    async def set(self, key: str, value) -> None:
        self._d[key] = value


def _room_principal() -> ExternalRoomPrincipal:
    return ExternalRoomPrincipal(
        tenant_id="tenant-1", external_party_id="ep_1", session_id="ers_1", grant_id="eag_1",
        room_id="dcgrp_1", permissions=int(ResourceAction.READ), email="viewer@example.com",
        display_name="Viewer", can_download=False, can_print=False,
    )


@pytest.mark.asyncio
async def test_room_viewer_blocks_open_until_nda_accepted():
    storage = MemoryStorage()
    obj = _ObjectStorage()
    nda = NdaService(storage=storage, object_storage=obj)
    await _make_document(storage, doc_id="doc_1", room_id="dcgrp_1")
    room_policy = await nda.set_policy(
        tenant_id="tenant-1", scope_type=NdaScopeType.ROOM, scope_id="dcgrp_1", created_by="u",
        content_type=NdaContentType.TEXT, text_body="Please accept.",
    )
    viewer = ExternalRoomViewerService(
        storage=storage, object_storage=obj, rendered_page_cache=_CacheStub(),
        document_processor=_ProcessorStub(), document_service=DocumentService(storage, event_bus=None),  # type: ignore[arg-type]
        nda_service=nda,
    )
    principal = _room_principal()

    with pytest.raises(NdaAcceptanceRequired):
        await viewer.create_view_session(principal=principal, document_id="doc_1")

    await nda.accept(
        policy=room_policy, subject=NdaService.subject_from_room_principal(principal),
        typed_name="Jane", scroll_confirmed=True, checkbox_confirmed=True,
    )
    delivery = await viewer.create_view_session(principal=principal, document_id="doc_1")
    assert delivery.resolved.document_id == "doc_1"

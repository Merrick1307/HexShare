from __future__ import annotations

from datetime import datetime

import pytest

from app.adapters import MemoryStorage
from app.core.authz import ResourceAction
from app.core.watermark_identity import pseudonymous_watermark
from app.domain import Document, DocumentGroup
from app.ports.object_storage_port import ObjectDescriptor, ObjectStoragePort, ObjectWriteRequest, TemporaryObjectAccess
from app.ports.rendered_page_cache_port import RenderedPageCachePort
from app.services import (
    DocumentProcessor,
    DocumentService,
    ExternalRoomPrincipal,
    ExternalRoomViewerService,
    PdfPreview,
    ProcessedDocument,
    ProcessingContext,
    RenderedPage,
    ViewPolicy,
)


class _ObjectStorageStub(ObjectStoragePort):
    def __init__(self) -> None:
        self.read_requests: list[str] = []

    def build_object_key(self, *, tenant_id: str, document_id: str, filename: str) -> str:
        return f"{tenant_id}/{document_id}/{filename}"

    async def read_object(self, *, object_key: str) -> bytes:
        self.read_requests.append(object_key)
        return b"source-bytes"

    async def write_object(self, request: ObjectWriteRequest) -> ObjectDescriptor:
        return ObjectDescriptor(object_key=request.object_key, size=len(request.content), content_type=request.content_type)

    async def create_temporary_upload(self, *, object_key: str, content_type: str, expires_in: int = 900) -> TemporaryObjectAccess:
        return TemporaryObjectAccess(object_key=object_key, url="https://upload.test")

    async def create_temporary_download(self, *, object_key: str, expires_in: int = 900, filename: str | None = None) -> TemporaryObjectAccess:
        return TemporaryObjectAccess(object_key=object_key, url="https://download.test", method="GET")

    async def head_object(self, *, object_key: str) -> ObjectDescriptor | None:
        return None

    async def delete_object(self, *, object_key: str) -> None:
        return None


class _RenderedPageCacheStub(RenderedPageCachePort):
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value) -> None:
        self._data[key] = value


class _ProcessorSpy(DocumentProcessor):
    def __init__(self, *, view_policy: ViewPolicy) -> None:
        super().__init__()
        self._view_policy = view_policy
        self.view_calls: list[tuple[ProcessingContext, bytes]] = []
        self.download_calls: list[tuple[ProcessingContext, bytes]] = []
        self.render_calls: list[tuple[ProcessingContext, int, int | None, str | None]] = []

    def describe_view_policy(self, *, filename: str, source_media_type: str | None):
        return self._view_policy

    async def describe_pdf_preview(self, *, content: bytes, cache_key: str | None = None):
        return PdfPreview(page_count=3)

    async def process_for_view(self, *, context: ProcessingContext, content: bytes) -> ProcessedDocument:
        self.view_calls.append((context, content))
        return ProcessedDocument(
            content=b"processed-view",
            media_type="text/html; charset=utf-8",
            filename=context.filename,
            source_media_type=context.source_media_type,
            processing_applied=True,
        )

    async def process_for_download(self, *, context: ProcessingContext, content: bytes) -> ProcessedDocument:
        self.download_calls.append((context, content))
        return ProcessedDocument(
            content=b"processed-download",
            media_type="application/octet-stream",
            filename=context.filename,
            source_media_type=context.source_media_type,
            processing_applied=False,
        )

    async def render_pdf_page(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
        page_number: int,
        render_width: int | None = None,
        cache_key: str | None = None,
    ):
        self.render_calls.append((context, page_number, render_width, cache_key))
        return RenderedPage(
            content=b"page-image",
            media_type="image/png",
            page_number=page_number,
            total_pages=3,
            width=render_width or 1400,
            height=1800,
        )


async def _seed_group_and_document(storage: MemoryStorage, *, document_id: str, filename: str, mime_type: str) -> None:
    group = DocumentGroup(
        id="dcgrp_room1",
        tenant_id="tenant-1",
        name="Data Room",
        description="Due diligence",
        created_by="user-1",
        created_at=datetime.utcnow(),
    )
    await storage.save_document_group(group)
    await storage.save_document(
        Document(
            id=document_id,
            tenant_id="tenant-1",
            name=filename,
            mime_type=mime_type,
            size=128,
            storage_key=f"documents/{document_id}/{filename}",
            created_at=datetime.utcnow(),
            created_by="user-1",
            room_id="dcgrp_room1",
        )
    )


def _principal(*, can_download: bool = True, can_print: bool = False) -> ExternalRoomPrincipal:
    permissions = int(ResourceAction.READ)
    if can_download:
        permissions |= int(ResourceAction.EXPORT)
    return ExternalRoomPrincipal(
        tenant_id="tenant-1",
        external_party_id="ep_1",
        session_id="ers_1",
        grant_id="eag_1",
        room_id="dcgrp_room1",
        permissions=permissions,
        email="viewer@example.com",
        display_name="Viewer Name",
        can_download=can_download,
        can_print=can_print,
    )


@pytest.mark.asyncio
async def test_create_view_session_returns_delivery_and_records_open_event():
    storage = MemoryStorage()
    await _seed_group_and_document(storage, document_id="doc_1", filename="report.pdf", mime_type="application/pdf")
    processor = _ProcessorSpy(view_policy=ViewPolicy(inline_view_supported=True, view_kind="pdf"))
    service = ExternalRoomViewerService(
        storage=storage,
        object_storage=_ObjectStorageStub(),
        rendered_page_cache=_RenderedPageCacheStub(),
        document_processor=processor,
        document_service=DocumentService(storage, event_bus=None),  # type: ignore[arg-type]
    )

    delivery = await service.create_view_session(principal=_principal(can_download=True), document_id="doc_1")

    assert delivery.resolved.session_id == "ers_1.doc_1"
    assert delivery.resolved.can_download is True
    assert delivery.view_policy.view_kind == "pdf"
    assert delivery.pdf_preview is not None
    events = storage._external_room_events["tenant-1"]  # type: ignore[attr-defined]
    assert len(events) == 1
    assert events[0].event_type.value == "document_view_open"
    assert events[0].document_id == "doc_1"


@pytest.mark.asyncio
async def test_stream_and_download_apply_external_room_watermark():
    storage = MemoryStorage()
    await _seed_group_and_document(storage, document_id="doc_2", filename="notes.txt", mime_type="text/plain")
    processor = _ProcessorSpy(view_policy=ViewPolicy(inline_view_supported=True, view_kind="text"))
    object_storage = _ObjectStorageStub()
    service = ExternalRoomViewerService(
        storage=storage,
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        document_processor=processor,
        document_service=DocumentService(storage, event_bus=None),  # type: ignore[arg-type]
    )
    principal = _principal(can_download=True, can_print=True)

    viewed = await service.stream_document(principal=principal, session_id="ers_1.doc_2")
    downloaded = await service.download_document(principal=principal, session_id="ers_1.doc_2")

    assert viewed.content == b"processed-view"
    assert downloaded.content == b"processed-download"
    assert object_storage.read_requests == ["documents/doc_2/notes.txt"]
    assert len(processor.view_calls) == 1
    assert len(processor.download_calls) == 1
    expected_watermark = pseudonymous_watermark(
        "ers_1", "ep_1", "viewer@example.com"
    )
    assert processor.view_calls[0][0].watermark_text == expected_watermark
    assert processor.download_calls[0][0].watermark_text == expected_watermark


@pytest.mark.asyncio
async def test_render_document_page_uses_cache_for_repeated_requests():
    storage = MemoryStorage()
    await _seed_group_and_document(storage, document_id="doc_3", filename="report.pdf", mime_type="application/pdf")
    processor = _ProcessorSpy(view_policy=ViewPolicy(inline_view_supported=True, view_kind="pdf"))
    object_storage = _ObjectStorageStub()
    service = ExternalRoomViewerService(
        storage=storage,
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        document_processor=processor,
        document_service=DocumentService(storage, event_bus=None),  # type: ignore[arg-type]
    )

    first = await service.render_document_page(
        principal=_principal(can_download=False),
        session_id="ers_1.doc_3",
        page_number=2,
        render_width=1200,
    )
    second = await service.render_document_page(
        principal=_principal(can_download=False),
        session_id="ers_1.doc_3",
        page_number=2,
        render_width=1200,
    )

    assert first.content == b"page-image"
    assert second.content == b"page-image"
    assert object_storage.read_requests == ["documents/doc_3/report.pdf"]
    assert len(processor.render_calls) == 1


@pytest.mark.asyncio
async def test_record_page_view_and_close_update_room_page_durations():
    storage = MemoryStorage()
    await _seed_group_and_document(storage, document_id="doc_4", filename="report.pdf", mime_type="application/pdf")
    processor = _ProcessorSpy(view_policy=ViewPolicy(inline_view_supported=True, view_kind="pdf"))
    service = ExternalRoomViewerService(
        storage=storage,
        object_storage=_ObjectStorageStub(),
        rendered_page_cache=_RenderedPageCacheStub(),
        document_processor=processor,
        document_service=DocumentService(storage, event_bus=None),  # type: ignore[arg-type]
    )
    principal = _principal(can_download=False)
    service._now = staticmethod(lambda: datetime(2026, 5, 16, 12, 0, 0))  # type: ignore[method-assign]
    await service.record_page_view(principal=principal, session_id="ers_1.doc_4", page_number=1)
    service._now = staticmethod(lambda: datetime(2026, 5, 16, 12, 0, 4))  # type: ignore[method-assign]
    await service.record_page_view(principal=principal, session_id="ers_1.doc_4", page_number=2)
    service._now = staticmethod(lambda: datetime(2026, 5, 16, 12, 0, 9))  # type: ignore[method-assign]
    await service.close_view_session(principal=principal, session_id="ers_1.doc_4")

    events = [event for event in storage._external_room_events["tenant-1"] if event.document_id == "doc_4"]  # type: ignore[attr-defined]
    page_events = [event for event in events if event.event_type == "document_page_view"]
    close_events = [event for event in events if event.event_type == "document_view_close"]

    assert len(page_events) == 2
    assert page_events[0].page_number == 1
    assert page_events[0].duration_ms == 4000
    assert page_events[1].page_number == 2
    assert page_events[1].duration_ms == 5000
    assert len(close_events) == 1

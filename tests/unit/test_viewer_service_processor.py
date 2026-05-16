from __future__ import annotations

from datetime import datetime

import pytest

from app.domain import VisitorSession
from app.ports.object_storage_port import ObjectDescriptor, ObjectStoragePort, ObjectWriteRequest, TemporaryObjectAccess
from app.services.document_processor import DocumentProcessor, ProcessedDocument, ProcessingContext
from app.services.viewer_service import ResolvedViewSession, ViewerService


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


class _ProcessorSpy(DocumentProcessor):
    def __init__(self) -> None:
        self.view_calls: list[tuple[ProcessingContext, bytes]] = []
        self.download_calls: list[tuple[ProcessingContext, bytes]] = []

    async def process_for_view(self, *, context: ProcessingContext, content: bytes) -> ProcessedDocument:
        self.view_calls.append((context, content))
        return ProcessedDocument(
            content=b"processed-view",
            media_type="application/pdf",
            filename=context.filename,
            source_media_type=context.source_media_type,
            processing_applied=True,
        )

    async def process_for_download(self, *, context: ProcessingContext, content: bytes) -> ProcessedDocument:
        self.download_calls.append((context, content))
        return ProcessedDocument(
            content=b"processed-download",
            media_type="application/pdf",
            filename=context.filename,
            source_media_type=context.source_media_type,
            processing_applied=True,
        )


def _resolved_session(*, email: str | None) -> ResolvedViewSession:
    return ResolvedViewSession(
        session=VisitorSession(
            id="vs_1",
            tenant_id="tenant-1",
            share_link_id="link-1",
            visitor_id=email,
            started_at=datetime(2026, 5, 16, 12, 0, 0),
            ended_at=None,
        ),
        link_id="link-1",
        document_id="doc-1",
        document_name="report.pdf",
        mime_type="application/pdf",
        size=128,
        storage_key="documents/doc-1/report.pdf",
        can_download=True,
        can_print=True,
        require_email=False,
        allowed_emails=[],
        email=email,
    )


@pytest.mark.asyncio
async def test_stream_document_uses_document_processor():
    object_storage = _ObjectStorageStub()
    processor = _ProcessorSpy()
    service = ViewerService(
        storage=None,  # type: ignore[arg-type]
        object_storage=object_storage,
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")

    async def fake_resolve(*, session_id: str):
        return active

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    service.resolve_view_session = fake_resolve  # type: ignore[method-assign]
    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    result = await service.stream_document(session_id="vs_1")

    assert result.content == b"processed-view"
    assert object_storage.read_requests == ["documents/doc-1/report.pdf"]
    assert len(processor.view_calls) == 1
    context, content = processor.view_calls[0]
    assert content == b"source-bytes"
    assert context.document_id == "doc-1"
    assert context.session_id == "vs_1"
    assert context.watermark_text == "HexShare - viewer@example.com"
    assert context.download is False


@pytest.mark.asyncio
async def test_download_document_uses_document_processor_with_link_watermark_when_email_missing():
    object_storage = _ObjectStorageStub()
    processor = _ProcessorSpy()
    service = ViewerService(
        storage=None,  # type: ignore[arg-type]
        object_storage=object_storage,
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email=None)

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    result = await service.download_document(tenant_id="tenant-1", session_id="vs_1")

    assert result.content == b"processed-download"
    assert object_storage.read_requests == ["documents/doc-1/report.pdf"]
    assert len(processor.download_calls) == 1
    context, content = processor.download_calls[0]
    assert content == b"source-bytes"
    assert context.watermark_text == "HexShare - link-1"
    assert context.download is True


@pytest.mark.asyncio
async def test_describe_view_session_delivery_uses_processor_view_policy():
    object_storage = _ObjectStorageStub()
    processor = DocumentProcessor()
    service = ViewerService(
        storage=None,  # type: ignore[arg-type]
        object_storage=object_storage,
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email=None)
    active = ResolvedViewSession(
        **{
            **active.__dict__,
            "document_name": "report.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    )

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    delivery = await service.describe_view_session_delivery(tenant_id="tenant-1", session_id="vs_1")

    assert delivery.resolved.document_name == "report.docx"
    assert delivery.view_policy.inline_view_supported is False
    assert delivery.view_policy.view_kind == "docx"
    assert delivery.view_policy.reason == "inline_view_not_supported"

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain import VisitorSession
from app.ports.object_storage_port import ObjectDescriptor, ObjectStoragePort, ObjectWriteRequest, TemporaryObjectAccess
from app.ports.rendered_page_cache_port import RenderedPageCachePort
from app.ports.task_queue_port import TaskQueuePort
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
        self.pdf_preview_contents: list[tuple[bytes, str | None]] = []
        self.render_page_calls: list[tuple[ProcessingContext, bytes, int, int | None, str | None]] = []

    def describe_view_policy(self, *, filename: str, source_media_type: str | None):
        if filename.endswith(".pdf"):
            return super().describe_view_policy(filename="report.txt", source_media_type="text/plain")
        return super().describe_view_policy(filename=filename, source_media_type=source_media_type)

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

    async def describe_pdf_preview(self, *, content: bytes, cache_key: str | None = None):
        self.pdf_preview_contents.append((content, cache_key))
        from app.services.document_processor import PdfPreview

        return PdfPreview(page_count=4)

    async def render_pdf_page(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
        page_number: int,
        render_width: int | None = None,
        cache_key: str | None = None,
    ):
        self.render_page_calls.append((context, content, page_number, render_width, cache_key))
        from app.services.document_processor import RenderedPage

        return RenderedPage(
            content=b"page-image",
            media_type="image/png",
            page_number=page_number,
            total_pages=4,
            width=render_width or 1400,
            height=1800,
        )


class _RenderedPageCacheStub(RenderedPageCachePort):
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value) -> None:
        self._data[key] = value


class _TaskQueueStub(TaskQueuePort):
    def __init__(self) -> None:
        self.jobs: list[tuple[str, int, int | None]] = []

    async def enqueue_prerender_page(
        self,
        *,
        session_id: str,
        page_number: int,
        render_width: int | None,
    ) -> None:
        self.jobs.append((session_id, page_number, render_width))


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
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")
    active = ResolvedViewSession(
        **{
            **active.__dict__,
            "document_name": "report.txt",
            "mime_type": "text/plain",
            "storage_key": "documents/doc-1/report.txt",
        }
    )

    async def fake_resolve(*, session_id: str):
        return active

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    service.resolve_view_session = fake_resolve  # type: ignore[method-assign]
    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    result = await service.stream_document(session_id="vs_1")

    assert result.content == b"processed-view"
    assert object_storage.read_requests == ["documents/doc-1/report.txt"]
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
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
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
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
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


@pytest.mark.asyncio
async def test_describe_view_session_delivery_loads_pdf_preview_metadata():
    object_storage = _ObjectStorageStub()
    processor = _ProcessorSpy()
    service = ViewerService(
        storage=None,  # type: ignore[arg-type]
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    processor.describe_view_policy = DocumentProcessor.describe_view_policy.__get__(processor, _ProcessorSpy)  # type: ignore[method-assign]
    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    delivery = await service.describe_view_session_delivery(tenant_id="tenant-1", session_id="vs_1")

    assert delivery.view_policy.view_kind == "pdf"
    assert delivery.pdf_preview is not None
    assert delivery.pdf_preview.page_count == 4
    assert object_storage.read_requests == ["documents/doc-1/report.pdf"]
    assert processor.pdf_preview_contents == [(b"source-bytes", "documents/doc-1/report.pdf")]


@pytest.mark.asyncio
async def test_render_document_page_uses_processor_and_records_page_view():
    object_storage = _ObjectStorageStub()

    class _StorageStub:
        def __init__(self) -> None:
            self.events = []
            self.latest_page_view = None
            self.updated_durations: list[tuple[str, int]] = []

        def generate_id(self, prefix: str) -> str:
            return f"{prefix}_1"

        async def save_view_event(self, event) -> None:
            self.events.append(event)
            if getattr(event, "event_type", None) == "page_view":
                self.latest_page_view = event

        async def get_latest_page_view_event(self, *, tenant_id: str, visitor_session_id: str):
            return self.latest_page_view

        async def update_view_event_duration(self, *, tenant_id: str, event_id: str, duration_ms: int) -> None:
            self.updated_durations.append((event_id, duration_ms))

    storage = _StorageStub()
    processor = _ProcessorSpy()
    service = ViewerService(
        storage=storage,  # type: ignore[arg-type]
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")

    async def fake_resolve(*, session_id: str):
        return active

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    processor.describe_view_policy = DocumentProcessor.describe_view_policy.__get__(processor, _ProcessorSpy)  # type: ignore[method-assign]
    service.resolve_view_session = fake_resolve  # type: ignore[method-assign]
    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    rendered = await service.render_document_page(session_id="vs_1", page_number=2, render_width=1200)

    assert rendered.content == b"page-image"
    assert object_storage.read_requests == ["documents/doc-1/report.pdf"]
    assert len(processor.render_page_calls) == 1
    context, content, page_number, render_width, cache_key = processor.render_page_calls[0]
    assert content == b"source-bytes"
    assert context.watermark_text == "HexShare - viewer@example.com"
    assert page_number == 2
    assert render_width == 1200
    assert cache_key == "documents/doc-1/report.pdf"
    assert len(storage.events) == 0


@pytest.mark.asyncio
async def test_render_document_page_uses_rendered_page_cache_for_repeated_page_request():
    object_storage = _ObjectStorageStub()

    class _StorageStub:
        def __init__(self) -> None:
            self.events = []
            self.latest_page_view = None
            self.updated_durations: list[tuple[str, int]] = []

        def generate_id(self, prefix: str) -> str:
            return f"{prefix}_1"

        async def save_view_event(self, event) -> None:
            self.events.append(event)
            if getattr(event, "event_type", None) == "page_view":
                self.latest_page_view = event

        async def get_latest_page_view_event(self, *, tenant_id: str, visitor_session_id: str):
            return self.latest_page_view

        async def update_view_event_duration(self, *, tenant_id: str, event_id: str, duration_ms: int) -> None:
            self.updated_durations.append((event_id, duration_ms))

    storage = _StorageStub()
    processor = _ProcessorSpy()
    service = ViewerService(
        storage=storage,  # type: ignore[arg-type]
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")

    async def fake_resolve(*, session_id: str):
        return active

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    processor.describe_view_policy = DocumentProcessor.describe_view_policy.__get__(processor, _ProcessorSpy)  # type: ignore[method-assign]
    service.resolve_view_session = fake_resolve  # type: ignore[method-assign]
    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    first = await service.render_document_page(session_id="vs_1", page_number=2, render_width=1200)
    second = await service.render_document_page(session_id="vs_1", page_number=2, render_width=1200)

    assert first.content == b"page-image"
    assert second.content == b"page-image"
    assert len(processor.render_page_calls) == 1
    assert object_storage.read_requests == ["documents/doc-1/report.pdf"]


@pytest.mark.asyncio
async def test_record_page_view_saves_page_view_event():
    object_storage = _ObjectStorageStub()

    class _StorageStub:
        def __init__(self) -> None:
            self.events = []
            self.latest_page_view = None
            self.updated_durations: list[tuple[str, int]] = []

        def generate_id(self, prefix: str) -> str:
            return f"{prefix}_1"

        async def save_view_event(self, event) -> None:
            self.events.append(event)
            if getattr(event, "event_type", None) == "page_view":
                self.latest_page_view = event

        async def get_latest_page_view_event(self, *, tenant_id: str, visitor_session_id: str):
            return self.latest_page_view

        async def update_view_event_duration(self, *, tenant_id: str, event_id: str, duration_ms: int) -> None:
            self.updated_durations.append((event_id, duration_ms))

    storage = _StorageStub()
    processor = _ProcessorSpy()
    service = ViewerService(
        storage=storage,  # type: ignore[arg-type]
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    await service.record_page_view(tenant_id="tenant-1", session_id="vs_1", page_number=5)

    assert len(storage.events) == 1
    assert storage.events[0].page_number == 5
    assert storage.events[0].duration_ms is None


@pytest.mark.asyncio
async def test_record_page_view_updates_previous_page_duration():
    object_storage = _ObjectStorageStub()

    class _StorageStub:
        def __init__(self) -> None:
            self.events = []
            self.latest_page_view = type(
                "PageViewEventStub",
                (),
                {
                    "id": "evt_prev",
                    "timestamp": datetime(2026, 5, 16, 12, 0, 0),
                    "duration_ms": None,
                },
            )()
            self.updated_durations: list[tuple[str, int]] = []

        def generate_id(self, prefix: str) -> str:
            return f"{prefix}_1"

        async def save_view_event(self, event) -> None:
            self.events.append(event)
            self.latest_page_view = event

        async def get_latest_page_view_event(self, *, tenant_id: str, visitor_session_id: str):
            return self.latest_page_view

        async def update_view_event_duration(self, *, tenant_id: str, event_id: str, duration_ms: int) -> None:
            self.updated_durations.append((event_id, duration_ms))

    storage = _StorageStub()
    processor = _ProcessorSpy()
    service = ViewerService(
        storage=storage,  # type: ignore[arg-type]
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
        document_processor=processor,
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]
    service._now = staticmethod(lambda: datetime(2026, 5, 16, 12, 0, 4))  # type: ignore[method-assign]

    await service.record_page_view(tenant_id="tenant-1", session_id="vs_1", page_number=5)

    assert storage.updated_durations == [("evt_prev", 4000)]
    assert len(storage.events) == 1
    assert storage.events[0].page_number == 5
    assert storage.events[0].duration_ms is None


@pytest.mark.asyncio
async def test_record_page_view_enqueues_next_page_job():
    object_storage = _ObjectStorageStub()

    class _StorageStub:
        def generate_id(self, prefix: str) -> str:
            return f"{prefix}_1"

        async def save_view_event(self, event) -> None:
            return None

        async def get_latest_page_view_event(self, *, tenant_id: str, visitor_session_id: str):
            return None

        async def update_view_event_duration(self, *, tenant_id: str, event_id: str, duration_ms: int) -> None:
            return None

    queue = _TaskQueueStub()
    service = ViewerService(
        storage=_StorageStub(),  # type: ignore[arg-type]
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=queue,
        document_processor=_ProcessorSpy(),
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")

    async def fake_ensure(*, tenant_id: str, session_id: str):
        return active

    service.ensure_active_session = fake_ensure  # type: ignore[method-assign]

    await service.record_page_view(tenant_id="tenant-1", session_id="vs_1", page_number=5)

    assert queue.jobs == [("vs_1", 6, None)]


@pytest.mark.asyncio
async def test_close_session_updates_last_page_duration_before_closing():
    object_storage = _ObjectStorageStub()

    class _StorageStub:
        def __init__(self) -> None:
            self.ended = []
            self.saved_events = []
            self.updated_durations: list[tuple[str, int]] = []
            self.latest_page_view = type(
                "PageViewEventStub",
                (),
                {
                    "id": "evt_prev",
                    "timestamp": datetime(2026, 5, 16, 12, 0, 0),
                    "duration_ms": None,
                },
            )()

        def generate_id(self, prefix: str) -> str:
            return f"{prefix}_1"

        async def get_latest_page_view_event(self, *, tenant_id: str, visitor_session_id: str):
            return self.latest_page_view

        async def update_view_event_duration(self, *, tenant_id: str, event_id: str, duration_ms: int) -> None:
            self.updated_durations.append((event_id, duration_ms))

        async def end_visitor_session(self, *, tenant_id: str, session_id: str, ended_at: datetime) -> None:
            self.ended.append((tenant_id, session_id, ended_at))

        async def save_view_event(self, event) -> None:
            self.saved_events.append(event)

    storage = _StorageStub()
    service = ViewerService(
        storage=storage,  # type: ignore[arg-type]
        object_storage=object_storage,
        rendered_page_cache=_RenderedPageCacheStub(),
        task_queue=_TaskQueueStub(),
        document_processor=_ProcessorSpy(),
        document_service=None,  # type: ignore[arg-type]
        link_service=None,  # type: ignore[arg-type]
    )

    active = _resolved_session(email="viewer@example.com")

    async def fake_resolve(*, tenant_id: str, session_id: str):
        return active

    service.resolve_view_session_for_tenant = fake_resolve  # type: ignore[method-assign]
    service._now = staticmethod(lambda: datetime(2026, 5, 16, 12, 0, 7))  # type: ignore[method-assign]

    await service.close_session(tenant_id="tenant-1", session_id="vs_1")

    assert storage.updated_durations == [("evt_prev", 7000)]
    assert len(storage.ended) == 1
    assert len(storage.saved_events) == 1
    assert storage.saved_events[0].event_type.value == "close"

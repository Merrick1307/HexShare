from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.services.document_processor import DocumentProcessingError, ProcessedDocument


@dataclass
class _Session:
    tenant_id: str = "tenant-1"
    ended_at: datetime | None = None


@dataclass
class _ResolvedSession:
    session: _Session
    can_download: bool = True


class _ViewerServiceStub:
    def __init__(self) -> None:
        self.download_attempts: list[tuple[str, str, bool]] = []
        self.page_views: list[tuple[str, str, int]] = []

    async def stream_document(self, *, session_id: str) -> ProcessedDocument:
        return ProcessedDocument(
            content=b"viewer-bytes",
            media_type="application/pdf",
            filename="report.pdf",
            source_media_type="application/pdf",
        )

    async def render_document_page(self, *, session_id: str, page_number: int, render_width: int | None = None):
        return type(
            "RenderedPageStub",
            (),
            {
                "content": b"png-bytes",
                "media_type": "image/png",
                "page_number": page_number,
                "total_pages": 2,
                "width": render_width or 1400,
                "height": 1800,
            },
        )()

    async def resolve_view_session(self, *, session_id: str) -> _ResolvedSession:
        return _ResolvedSession(session=_Session())

    async def ensure_active_session(self, *, tenant_id: str, session_id: str) -> _ResolvedSession:
        return _ResolvedSession(session=_Session(), can_download=True)

    async def record_download_attempt(self, *, tenant_id: str, session_id: str, blocked: bool = False) -> None:
        self.download_attempts.append((tenant_id, session_id, blocked))

    async def download_document(self, *, tenant_id: str, session_id: str) -> ProcessedDocument:
        return ProcessedDocument(
            content=b"download-bytes",
            media_type="application/pdf",
            filename="report.pdf",
            source_media_type="application/pdf",
        )

    async def record_page_view(self, *, tenant_id: str, session_id: str, page_number: int) -> None:
        self.page_views.append((tenant_id, session_id, page_number))


def _make_client(viewer_service: _ViewerServiceStub) -> TestClient:
    app = FastAPI()
    app.include_router(api_router(), prefix="/api/v1")
    app.state.viewer_service = viewer_service
    return TestClient(app)


def test_view_content_applies_hardened_inline_headers():
    client = _make_client(_ViewerServiceStub())

    response = client.get("/api/v1/view-sessions/session-1/content")

    assert response.status_code == 200
    assert response.content == b"viewer-bytes"
    assert response.headers["content-disposition"] == 'inline; filename="report.pdf"'
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex, noarchive, nosnippet"
    assert response.headers["x-frame-options"] == "DENY"


def test_download_route_applies_hardened_attachment_headers():
    client = _make_client(_ViewerServiceStub())

    response = client.get("/api/v1/view-sessions/session-1/download")

    assert response.status_code == 200
    assert response.content == b"download-bytes"
    assert response.headers["content-disposition"] == 'attachment; filename="report.pdf"'
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex, noarchive, nosnippet"
    assert response.headers["x-frame-options"] == "DENY"


def test_download_route_blocks_when_download_disabled():
    service = _ViewerServiceStub()

    async def disabled_session(*, tenant_id: str, session_id: str) -> _ResolvedSession:
        return _ResolvedSession(session=_Session(), can_download=False)

    service.ensure_active_session = disabled_session  # type: ignore[method-assign]
    client = _make_client(service)

    response = client.get("/api/v1/view-sessions/session-1/download")

    assert response.status_code == 403
    assert response.json()["detail"] == "Downloads are disabled for this share link"
    assert service.download_attempts == [("tenant-1", "session-1", True)]


def test_view_content_returns_415_for_unsupported_inline_format():
    service = _ViewerServiceStub()

    async def unsupported_stream(*, session_id: str) -> ProcessedDocument:
        raise DocumentProcessingError("inline_view_not_supported")

    service.stream_document = unsupported_stream  # type: ignore[method-assign]
    client = _make_client(service)

    response = client.get("/api/v1/view-sessions/session-1/content")

    assert response.status_code == 415
    assert response.json()["detail"] == "inline_view_not_supported"


def test_view_content_returns_409_when_pdf_uses_page_image_mode():
    service = _ViewerServiceStub()

    async def page_image_required(*, session_id: str) -> ProcessedDocument:
        raise DocumentProcessingError("page_image_view_required")

    service.stream_document = page_image_required  # type: ignore[method-assign]
    client = _make_client(service)

    response = client.get("/api/v1/view-sessions/session-1/content")

    assert response.status_code == 409
    assert response.json()["detail"] == "page_image_view_required"


def test_page_image_route_applies_hardened_inline_headers():
    client = _make_client(_ViewerServiceStub())

    response = client.get("/api/v1/view-sessions/session-1/pages/1?width=1200")

    assert response.status_code == 200
    assert response.content == b"png-bytes"
    assert response.headers["content-disposition"] == 'inline; filename="session-1-page-1.png"'
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex, noarchive, nosnippet"
    assert response.headers["x-frame-options"] == "DENY"


def test_page_view_route_records_page_view_event():
    service = _ViewerServiceStub()
    client = _make_client(service)

    response = client.post("/api/v1/view-sessions/session-1/page-view?page_number=3")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert service.page_views == [("tenant-1", "session-1", 3)]

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

    async def stream_document(self, *, session_id: str) -> ProcessedDocument:
        return ProcessedDocument(
            content=b"viewer-bytes",
            media_type="application/pdf",
            filename="report.pdf",
            source_media_type="application/pdf",
        )

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

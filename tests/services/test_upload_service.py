from __future__ import annotations

import pytest

from app.adapters import MemoryStorage, NoopEventBus
from app.domain import Document
from app.ports.object_storage_port import ObjectInfo, ObjectStoragePort, ObjectWriteRequest, TemporaryObjectAccess
from app.services.document_service import DocumentService
from app.services.upload_service import UploadService


class InMemoryObjectStorage(ObjectStoragePort):
    def __init__(self) -> None:
        self._objects: dict[str, ObjectInfo] = {}
        self._content: dict[str, bytes] = {}

    def put_object(self, *, object_key: str, size: int, etag: str | None = None, content_type: str | None = None):
        self._objects[object_key] = ObjectInfo(
            object_key=object_key,
            size=size,
            etag=etag,
            content_type=content_type,
            metadata={},
        )

    def build_object_key(self, *, tenant_id: str, document_id: str, filename: str) -> str:
        return f"documents/tenants/{tenant_id}/documents/{document_id}/{filename}"

    async def read_object(self, *, object_key: str) -> bytes:
        return self._content.get(object_key, b"")

    async def write_object(self, request: ObjectWriteRequest) -> ObjectInfo:
        self._content[request.object_key] = request.content
        info = ObjectInfo(
            object_key=request.object_key,
            size=len(request.content),
            etag=None,
            content_type=request.content_type,
            metadata=dict(request.metadata or {}),
        )
        self._objects[request.object_key] = info
        return info

    async def create_temporary_upload(self, *, object_key: str, content_type: str, expires_in: int = 900) -> TemporaryObjectAccess:
        return TemporaryObjectAccess(
            object_key=object_key,
            url=f"https://objects.test/upload/{object_key}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=expires_in,
        )

    async def create_temporary_download(self, *, object_key: str, expires_in: int = 900, filename: str | None = None) -> TemporaryObjectAccess:
        return TemporaryObjectAccess(
            object_key=object_key,
            url=f"https://objects.test/download/{object_key}?expires_in={expires_in}",
            method="GET",
            expires_in=expires_in,
        )

    async def head_object(self, *, object_key: str) -> ObjectInfo | None:
        return self._objects.get(object_key)

    async def delete_object(self, *, object_key: str) -> None:
        self._objects.pop(object_key, None)


def _make_service(max_size_bytes: int | None = None) -> tuple[UploadService, InMemoryObjectStorage, MemoryStorage]:
    metadata_storage = MemoryStorage()
    document_service = DocumentService(metadata_storage, NoopEventBus())
    object_storage = InMemoryObjectStorage()
    service = UploadService(
        metadata_storage=metadata_storage,
        object_storage=object_storage,
        document_service=document_service,
        max_size_bytes=max_size_bytes,
    )
    return service, object_storage, metadata_storage


# ── initiate_upload ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initiate_upload_rejects_size_above_max():
    service, _, _ = _make_service(max_size_bytes=1024)

    with pytest.raises(ValueError, match="upload_size_exceeded"):
        await service.initiate_upload(
            tenant_id="tenant_1",
            filename="big.pdf",
            content_type="application/pdf",
            size=2048,
        )


@pytest.mark.asyncio
async def test_initiate_upload_allows_size_at_max():
    service, _, _ = _make_service(max_size_bytes=1024)

    started = await service.initiate_upload(
        tenant_id="tenant_1",
        filename="exact.pdf",
        content_type="application/pdf",
        size=1024,
    )

    assert started.document_id.startswith("doc_")
    assert started.upload.method == "PUT"


@pytest.mark.asyncio
async def test_initiate_upload_allows_size_below_max():
    service, _, _ = _make_service(max_size_bytes=1024)

    started = await service.initiate_upload(
        tenant_id="tenant_1",
        filename="small.pdf",
        content_type="application/pdf",
        size=512,
    )

    assert started.document_id.startswith("doc_")


@pytest.mark.asyncio
async def test_initiate_upload_allows_any_size_when_max_is_none():
    service, _, _ = _make_service(max_size_bytes=None)

    started = await service.initiate_upload(
        tenant_id="tenant_1",
        filename="huge.pdf",
        content_type="application/pdf",
        size=10 * 1024 * 1024 * 1024,  # 10 GB
    )

    assert started.document_id.startswith("doc_")


# ── complete_upload ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_upload_rejects_size_above_max():
    service, object_storage, _ = _make_service(max_size_bytes=1024)

    object_key = "documents/tenants/tenant_1/documents/doc_1/big.pdf"
    object_storage.put_object(object_key=object_key, size=2048, etag="abc")

    with pytest.raises(ValueError, match="upload_size_exceeded"):
        await service.complete_upload(
            tenant_id="tenant_1",
            document_id="doc_1",
            object_key=object_key,
            name="big.pdf",
            mime_type="application/pdf",
            size=2048,
            created_by="user_1",
        )


@pytest.mark.asyncio
async def test_complete_upload_rejects_size_above_max_before_checking_object():
    """Size check must happen before any object storage call."""
    service, object_storage, _ = _make_service(max_size_bytes=1024)

    # Object doesn't even exist — size check should fail first
    with pytest.raises(ValueError, match="upload_size_exceeded"):
        await service.complete_upload(
            tenant_id="tenant_1",
            document_id="doc_1",
            object_key="documents/tenants/tenant_1/documents/doc_1/missing.pdf",
            name="missing.pdf",
            mime_type="application/pdf",
            size=2048,
            created_by="user_1",
        )


@pytest.mark.asyncio
async def test_complete_upload_allows_size_at_max():
    service, object_storage, _ = _make_service(max_size_bytes=1024)

    object_key = "documents/tenants/tenant_1/documents/doc_1/exact.pdf"
    object_storage.put_object(object_key=object_key, size=1024, etag="abc")

    document = await service.complete_upload(
        tenant_id="tenant_1",
        document_id="doc_1",
        object_key=object_key,
        name="exact.pdf",
        mime_type="application/pdf",
        size=1024,
        created_by="user_1",
    )

    assert isinstance(document, Document)
    assert document.size == 1024


@pytest.mark.asyncio
async def test_complete_upload_allows_size_below_max():
    service, object_storage, _ = _make_service(max_size_bytes=1024)

    object_key = "documents/tenants/tenant_1/documents/doc_1/small.pdf"
    object_storage.put_object(object_key=object_key, size=512, etag="abc")

    document = await service.complete_upload(
        tenant_id="tenant_1",
        document_id="doc_1",
        object_key=object_key,
        name="small.pdf",
        mime_type="application/pdf",
        size=512,
        created_by="user_1",
    )

    assert isinstance(document, Document)
    assert document.size == 512


@pytest.mark.asyncio
async def test_complete_upload_allows_any_size_when_max_is_none():
    service, object_storage, _ = _make_service(max_size_bytes=None)

    object_key = "documents/tenants/tenant_1/documents/doc_1/huge.pdf"
    object_storage.put_object(object_key=object_key, size=10 * 1024 * 1024 * 1024, etag="abc")

    document = await service.complete_upload(
        tenant_id="tenant_1",
        document_id="doc_1",
        object_key=object_key,
        name="huge.pdf",
        mime_type="application/pdf",
        size=10 * 1024 * 1024 * 1024,
        created_by="user_1",
    )

    assert isinstance(document, Document)


# ── Edge cases ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_max_size_zero_rejects_everything():
    service, _, _ = _make_service(max_size_bytes=0)

    with pytest.raises(ValueError, match="upload_size_exceeded"):
        await service.initiate_upload(
            tenant_id="tenant_1",
            filename="tiny.pdf",
            content_type="application/pdf",
            size=1,
        )


@pytest.mark.asyncio
async def test_max_size_one_allows_single_byte():
    service, object_storage, _ = _make_service(max_size_bytes=1)

    object_key = "documents/tenants/tenant_1/documents/doc_1/one.pdf"
    object_storage.put_object(object_key=object_key, size=1, etag="abc")

    document = await service.complete_upload(
        tenant_id="tenant_1",
        document_id="doc_1",
        object_key=object_key,
        name="one.pdf",
        mime_type="application/pdf",
        size=1,
        created_by="user_1",
    )

    assert document.size == 1

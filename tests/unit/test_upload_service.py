from __future__ import annotations

from datetime import datetime

import pytest

from app.adapters import MemoryStorage, NoopEventBus
from app.domain import Document
from app.ports.object_storage_port import ObjectInfo, ObjectStoragePort, PresignedUpload
from app.services.document_service import DocumentService
from app.services.upload_service import UploadService


class InMemoryObjectStorage(ObjectStoragePort):
    def __init__(self) -> None:
        self._objects: dict[str, ObjectInfo] = {}

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

    async def create_presigned_upload(self, *, object_key: str, content_type: str, expires_in: int = 900) -> PresignedUpload:
        return PresignedUpload(
            object_key=object_key,
            url=f"https://objects.test/upload/{object_key}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=expires_in,
        )

    async def create_presigned_download(self, *, object_key: str, expires_in: int = 900, filename: str | None = None) -> str:
        return f"https://objects.test/download/{object_key}?expires_in={expires_in}"

    async def head_object(self, *, object_key: str) -> ObjectInfo | None:
        return self._objects.get(object_key)

    async def delete_object(self, *, object_key: str) -> None:
        self._objects.pop(object_key, None)


@pytest.fixture
def upload_service() -> tuple[UploadService, InMemoryObjectStorage, MemoryStorage]:
    metadata_storage = MemoryStorage()
    document_service = DocumentService(metadata_storage, NoopEventBus())
    object_storage = InMemoryObjectStorage()
    service = UploadService(
        metadata_storage=metadata_storage,
        object_storage=object_storage,
        document_service=document_service,
    )
    return service, object_storage, metadata_storage


@pytest.mark.asyncio
async def test_initiate_upload_returns_document_id_and_presigned_put(upload_service):
    service, _, _ = upload_service

    started = await service.initiate_upload(
        tenant_id="tenant_123",
        filename="report.pdf",
        content_type="application/pdf",
        size=1024,
    )

    assert started.document_id.startswith("doc_")
    assert started.object_key == f"documents/tenants/tenant_123/documents/{started.document_id}/report.pdf"
    assert started.upload.method == "PUT"
    assert started.upload.headers == {"Content-Type": "application/pdf"}
    assert "https://objects.test/upload/" in started.upload.url


@pytest.mark.asyncio
async def test_complete_upload_persists_document_when_object_exists(upload_service):
    service, object_storage, metadata_storage = upload_service

    object_key = "documents/tenants/tenant_123/documents/doc_42/report.pdf"
    object_storage.put_object(
        object_key=object_key,
        size=1024,
        etag="abc123",
        content_type="application/pdf",
    )

    document = await service.complete_upload(
        tenant_id="tenant_123",
        document_id="doc_42",
        object_key=object_key,
        name="Quarterly report.pdf",
        mime_type="application/pdf",
        size=1024,
        created_by="user_1",
        expected_etag="abc123",
    )

    assert isinstance(document, Document)
    assert document.id == "doc_42"
    assert document.storage_key == object_key

    saved = await metadata_storage.get_document(tenant_id="tenant_123", document_id="doc_42")
    assert saved is not None
    assert saved.name == "Quarterly report.pdf"


@pytest.mark.asyncio
async def test_complete_upload_rejects_size_mismatch(upload_service):
    service, object_storage, _ = upload_service

    object_key = "documents/tenants/tenant_123/documents/doc_43/report.pdf"
    object_storage.put_object(object_key=object_key, size=512, etag="etag-1")

    with pytest.raises(ValueError, match="object_size_mismatch"):
        await service.complete_upload(
            tenant_id="tenant_123",
            document_id="doc_43",
            object_key=object_key,
            name="report.pdf",
            mime_type="application/pdf",
            size=1024,
            created_by="user_1",
        )


@pytest.mark.asyncio
async def test_get_download_url_uses_saved_document_storage_key(upload_service):
    service, object_storage, _ = upload_service

    object_key = "documents/tenants/tenant_123/documents/doc_44/report.pdf"
    object_storage.put_object(object_key=object_key, size=2048, etag="etag-2")

    await service.complete_upload(
        tenant_id="tenant_123",
        document_id="doc_44",
        object_key=object_key,
        name="report.pdf",
        mime_type="application/pdf",
        size=2048,
        created_by="user_2",
    )

    url = await service.get_download_url(
        tenant_id="tenant_123",
        document_id="doc_44",
        expires_in=600,
    )

    assert url == f"https://objects.test/download/{object_key}?expires_in=600"

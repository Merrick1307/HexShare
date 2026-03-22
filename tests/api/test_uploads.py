from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.uploads import complete_upload, get_document_download_url, initiate_upload
from app.auth.tenant_auth import TenantPrincipal
from app.domain import Document
from app.ports.object_storage_port import PresignedUpload
from app.services.upload_service import UploadInitiation


class StubUploadService:
    def __init__(self):
        self.mode = "ok"

    async def initiate_upload(self, **kwargs):
        return UploadInitiation(
            document_id="doc_1",
            object_key="documents/tenants/t1/documents/doc_1/report.pdf",
            upload=PresignedUpload(
                object_key="documents/tenants/t1/documents/doc_1/report.pdf",
                url="https://storage.test/upload/doc_1",
                method="PUT",
                headers={"Content-Type": "application/pdf"},
                expires_in=900,
            ),
        )

    async def complete_upload(self, **kwargs):
        if self.mode == "exists":
            raise ValueError("document_already_exists")
        if self.mode == "missing":
            raise ValueError("object_not_found")
        if self.mode == "etag":
            raise ValueError("object_etag_mismatch")
        return Document(
            id="doc_1",
            tenant_id="tenant_1",
            name="report.pdf",
            mime_type="application/pdf",
            size=123,
            storage_key="documents/tenants/t1/documents/doc_1/report.pdf",
            created_at="2026-03-19T00:00:00",
            created_by="user_1",
        )

    async def get_download_url(self, **kwargs):
        return "https://storage.test/download/doc_1"


class StubDocumentService:
    def __init__(self, document: Document | None):
        self._document = document

    async def get_document(self, **kwargs):
        return self._document


@pytest.mark.asyncio
async def test_initiate_upload_handler_shapes_response():
    principal = TenantPrincipal(tenant_id="tenant_1", user_id="user_1")
    service = StubUploadService()

    class Payload:
        filename = "report.pdf"
        content_type = "application/pdf"
        size = 123
        expires_in = 900

    response = await initiate_upload(Payload(), principal=principal, upload_service=service)

    assert response.document_id == "doc_1"
    assert response.method == "PUT"
    assert response.required_headers["Content-Type"] == "application/pdf"


@pytest.mark.asyncio
async def test_complete_upload_handler_maps_domain_errors():
    principal = TenantPrincipal(tenant_id="tenant_1", user_id="user_1")
    service = StubUploadService()
    service.mode = "exists"

    class Payload:
        document_id = "doc_1"
        object_key = "documents/tenants/t1/documents/doc_1/report.pdf"
        name = "report.pdf"
        mime_type = "application/pdf"
        size = 123
        etag = None

    with pytest.raises(HTTPException) as exc:
        await complete_upload(Payload(), principal=principal, upload_service=service)

    assert exc.value.status_code == 409
    assert exc.value.detail == "Document already finalized"


@pytest.mark.asyncio
async def test_download_handler_returns_presigned_url():
    principal = TenantPrincipal(tenant_id="tenant_1", user_id="user_1")
    document = Document(
        id="doc_1",
        tenant_id="tenant_1",
        name="report.pdf",
        mime_type="application/pdf",
        size=123,
        storage_key="documents/tenants/t1/documents/doc_1/report.pdf",
        created_at="2026-03-19T00:00:00",
        created_by="user_1",
    )

    response = await get_document_download_url(
        document_id="doc_1",
        expires_in=900,
        principal=principal,
        document_service=StubDocumentService(document),
        upload_service=StubUploadService(),
    )

    assert response.document_id == "doc_1"
    assert response.download_url == "https://storage.test/download/doc_1"


@pytest.mark.asyncio
async def test_download_handler_404s_when_document_missing():
    principal = TenantPrincipal(tenant_id="tenant_1", user_id="user_1")

    with pytest.raises(HTTPException) as exc:
        await get_document_download_url(
            document_id="doc_404",
            expires_in=900,
            principal=principal,
            document_service=StubDocumentService(None),
            upload_service=StubUploadService(),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Document not found"

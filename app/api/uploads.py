from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies.services import get_document_service, get_upload_service
from app.auth import TenantPrincipal
from app.auth.tenant_auth import get_tenant_auth
from app.domain import Document
from app.schemas.upload import (
    CompleteUploadRequest,
    DownloadUrlResponse,
    InitiateUploadRequest,
    InitiateUploadResponse,
)
from app.services.document_service import DocumentService
from app.services.upload_service import UploadService

router = APIRouter(tags=["uploads"])


@router.post("/uploads/initiate", response_model=InitiateUploadResponse)
async def initiate_upload(
    payload: InitiateUploadRequest,
    principal: TenantPrincipal = Depends(get_tenant_auth()),
    upload_service: UploadService = Depends(get_upload_service),
) -> InitiateUploadResponse:
    initiated = await upload_service.initiate_upload(
        tenant_id=principal.tenant_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
        expires_in=payload.expires_in,
    )
    return InitiateUploadResponse(
        document_id=initiated.document_id,
        object_key=initiated.object_key,
        method=initiated.upload.method,
        upload_url=initiated.upload.url,
        expires_in=initiated.upload.expires_in,
        required_headers=dict(initiated.upload.headers or {}),
    )


@router.post("/uploads/complete", response_model=Document)
async def complete_upload(
    payload: CompleteUploadRequest,
    principal: TenantPrincipal = Depends(get_tenant_auth()),
    upload_service: UploadService = Depends(get_upload_service),
) -> Document:
    try:
        return await upload_service.complete_upload(
            tenant_id=principal.tenant_id,
            document_id=payload.document_id,
            object_key=payload.object_key,
            name=payload.name,
            mime_type=payload.mime_type,
            size=payload.size,
            created_by=principal.user_id,
            expected_etag=payload.etag,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "document_already_exists":
            raise HTTPException(status_code=409, detail="Document already finalized")
        if detail == "object_not_found":
            raise HTTPException(status_code=404, detail="Uploaded object not found")
        if detail in {"object_size_mismatch", "object_etag_mismatch"}:
            raise HTTPException(status_code=400, detail=detail)
        raise HTTPException(status_code=400, detail="Upload completion failed")


@router.get("/documents/{document_id}/download", response_model=DownloadUrlResponse)
async def get_document_download_url(
    document_id: str,
    expires_in: int = Query(default=900, ge=60, le=3600),
    principal: TenantPrincipal = Depends(get_tenant_auth()),
    document_service: DocumentService = Depends(get_document_service),
    upload_service: UploadService = Depends(get_upload_service),
) -> DownloadUrlResponse:
    document = await document_service.get_document(
        tenant_id=principal.tenant_id,
        document_id=document_id,
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    download_url = await upload_service.get_download_url(
        tenant_id=principal.tenant_id,
        document_id=document_id,
        expires_in=expires_in,
        filename=document.name,
    )
    return DownloadUrlResponse(
        document_id=document_id,
        download_url=download_url,
        expires_in=expires_in,
    )

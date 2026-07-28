from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.adapters.rate_limiting import rate_limit
from app.api.dependencies.services import (
    get_document_group_service,
    get_document_service,
    get_upload_service,
)
from app.auth import TenantPrincipal
from app.auth.tenant_auth import get_tenant_auth
from app.core.authz import ResourceAction
from app.domain import Document
from app.ports.access_control import AccessDenied
from app.schemas.upload import (
    CompleteUploadRequest,
    DownloadUrlResponse,
    InitiateUploadRequest,
    InitiateUploadResponse,
)
from app.services.document_service import DocumentService
from app.services.document_group_service import DocumentGroupService
from app.services.upload_service import UploadService


async def initiate_upload(
    payload: InitiateUploadRequest,
    principal: TenantPrincipal = Depends(get_tenant_auth()),
    upload_service: UploadService = Depends(get_upload_service),
) -> InitiateUploadResponse:
    try:
        initiated = await upload_service.initiate_upload(
            tenant_id=principal.tenant_id,
            filename=payload.filename,
            content_type=payload.content_type,
            size=payload.size,
            expires_in=payload.expires_in,
        )
    except ValueError as exc:
        if str(exc) == "upload_size_exceeded":
            raise HTTPException(status_code=413, detail="File size exceeds the maximum allowed")
        if str(exc) == "unsupported_document_type":
            raise HTTPException(
                status_code=415,
                detail={
                    "code": "unsupported_document_type",
                    "message": "Choose a supported business document: PDF, Office, text, CSV, Markdown, PNG, JPEG, or WebP.",
                },
            )
        raise
    return InitiateUploadResponse(
        document_id=initiated.document_id,
        object_key=initiated.object_key,
        method=initiated.upload.method,
        upload_url=initiated.upload.url,
        expires_in=initiated.upload.expires_in,
        required_headers=dict(initiated.upload.headers or {}),
        required_form_fields=dict(getattr(initiated.upload, "form_fields", {}) or {}),
        protection=initiated.protection,
    )


async def complete_upload(
    payload: CompleteUploadRequest,
    principal: TenantPrincipal = Depends(get_tenant_auth()),
    upload_service: UploadService = Depends(get_upload_service),
    group_service: DocumentGroupService = Depends(get_document_group_service),
) -> Document:
    try:
        room_id = getattr(payload, "room_id", None)
        room_section_id = getattr(payload, "room_section_id", None)
        if room_section_id and not room_id:
            raise HTTPException(
                status_code=400, detail="room_id is required when room_section_id is set"
            )
        if room_id:
            await group_service.get_group(
                principal=principal,
                group_id=room_id,
                required=ResourceAction.WRITE,
            )
            if room_section_id:
                sections = await group_service.list_sections(
                    principal=principal, group_id=room_id
                )
                if room_section_id not in {section.id for section in sections}:
                    raise HTTPException(status_code=404, detail="Room section not found")
        return await upload_service.complete_upload(
            tenant_id=principal.tenant_id,
            document_id=payload.document_id,
            object_key=payload.object_key,
            name=payload.name,
            mime_type=payload.mime_type,
            size=payload.size,
            created_by=principal.user_id,
            expected_etag=payload.etag,
            room_id=room_id,
            room_section_id=room_section_id,
        )
    except AccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError as exc:
        detail = str(exc)
        if detail == "document_already_exists":
            raise HTTPException(status_code=409, detail="Document already finalized")
        if detail == "object_not_found":
            raise HTTPException(status_code=404, detail="Uploaded object not found")
        if detail == "upload_size_exceeded":
            raise HTTPException(status_code=413, detail="File size exceeds the maximum allowed")
        if detail in {"object_size_mismatch", "object_etag_mismatch"}:
            raise HTTPException(status_code=400, detail=detail)
        if detail == "unsupported_document_type":
            raise HTTPException(
                status_code=415,
                detail={
                    "code": detail,
                    "message": "Choose a supported business document: PDF, Office, text, CSV, Markdown, PNG, JPEG, or WebP.",
                },
            )
        if detail == "corrupt_pdf":
            raise HTTPException(
                status_code=422,
                detail={"code": detail, "message": "This PDF is corrupt or cannot be read."},
            )
        if detail == "password_protected_pdf":
            raise HTTPException(
                status_code=422,
                detail={"code": detail, "message": "Upload an unlocked PDF for protected viewing."},
            )
        raise HTTPException(status_code=400, detail="Upload completion failed")


async def get_document_download_url(
    document_id: str,
    expires_in: int = Query(default=900, ge=60, le=3600),
    principal: TenantPrincipal = Depends(get_tenant_auth()),
    document_service: DocumentService = Depends(get_document_service),
    upload_service: UploadService = Depends(get_upload_service),
) -> DownloadUrlResponse:
    try:
        document = await document_service.require_document_access(
            principal=principal,
            document_id=document_id,
            required=ResourceAction.EXPORT,
        )
    except AccessDenied:
        raise HTTPException(status_code=403, detail="Forbidden")
    except ValueError:
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


def build_router() -> APIRouter:
    router = APIRouter(tags=["uploads"], dependencies=[Depends(rate_limit("document_upload"))])
    router.add_api_route(
        "/uploads/initiate",
        initiate_upload,
        methods=["POST"],
        response_model=InitiateUploadResponse,
    )
    router.add_api_route(
        "/uploads/complete",
        complete_upload,
        methods=["POST"],
        response_model=Document,
    )
    router.add_api_route(
        "/documents/{document_id}/download",
        get_document_download_url,
        methods=["GET"],
        response_model=DownloadUrlResponse,
    )
    return router

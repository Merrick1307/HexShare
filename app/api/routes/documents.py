from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.api.dependencies.services import (
    get_analytics_service,
    get_document_group_service,
    get_document_service,
    get_external_room_access_service,
    get_external_room_viewer_service,
    get_iam_policy,
    get_link_service,
    get_nda_service,
    get_share_auth,
    get_storage,
    get_upload_service,
    get_viewer_service,
)
from app.auth import ShareTokenClaims, TenantPrincipal
from app.auth.external_room_auth import get_external_room_principal
from app.auth.share_token_auth import ShareTokenDependency
from app.auth.tenant_auth import get_tenant_auth
from app.core.authz import EXTERNAL_AUTH_COOKIE, EXTERNAL_REFRESH_COOKIE, ResourceAction
from app.domain import Document, DocumentGroup, NdaContentType, NdaScopeType, ShareLink
from app.ports.access_control import AccessDenied
from app.schemas.nda import (
    NdaAcceptRequest,
    NdaAcceptResponse,
    NdaAcceptanceRecordView,
    NdaPolicyAdminView,
    NdaPolicyView,
    NdaStatusResponse,
    SetNdaTextRequest,
)
from app.schemas.external_room import (
    CreateExternalRoomSessionRequest,
    ExternalRoomContextResponse,
    ExternalRoomDocumentSessionResponse,
    ExternalRoomGrantResponse,
    ExternalRoomInviteInspectionResponse,
    ExternalRoomSessionResponse,
    ProvisionExternalRoomAccessResponse,
)
from app.schemas.pagination import PaginatedResponse
from app.schemas.rooms import PlaceDocumentRequest
from app.schemas.share import ShareLinkResponse
from app.schemas.workspace import (
    ActivityItemResponse,
    NdaPolicySummaryResponse,
    WorkspaceSummaryResponse,
)
from app.schemas.upload import DownloadUrlResponse
from app.schemas.viewer import (
    CreateViewSessionRequest,
    CreateViewSessionResponse,
    ShareLinkInspectionResponse,
)
from app.services import (
    AnalyticsService,
    DocumentGroupService,
    DocumentService,
    DocumentProcessingError,
    ExternalRoomAccessService,
    ExternalRoomDocumentSessionDelivery,
    ExternalRoomPrincipal,
    ExternalRoomViewerService,
    LinkService,
    NdaError,
    NdaService,
    NdaSubject,
    UploadService,
    ViewerService,
)
from app.adapters.rate_limiting import rate_limit
from app.api.helpers.utils import (
    _admin_policy_view,
    _apply_viewer_headers,
    _build_nda_status,
    _build_page_image_filename,
    _load_recipient_nda_policy,
    _secure_cookie,
    _serialize_external_room_document_session,
    _serialize_link,
    _stream_bytes,
)



def build_router() -> APIRouter:
    router = APIRouter(dependencies=[Depends(rate_limit("api_general"))])

    @router.post("/documents", response_model=Document)
    async def create_document(
        name: str = Query(..., description="Name of the document"),
        mime_type: str = Query(..., description="MIME type"),
        size: int = Query(..., description="Size in bytes"),
        storage_key: str = Query(..., description="Key in object storage"),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> Document:
        return await document_service.create_document(
            tenant_id=principal.tenant_id,
            name=name,
            mime_type=mime_type,
            size=size,
            storage_key=storage_key,
            created_by=principal.user_id,
        )

    @router.get("/documents", response_model=PaginatedResponse[Document])
    async def list_documents(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        query: Optional[str] = Query(None),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> PaginatedResponse[Document]:
        docs, total = await document_service.page_accessible_documents(
            principal=principal,
            query=query,
            offset=offset,
            limit=limit,
        )
        return PaginatedResponse(items=docs, total=total)

    @router.get("/documents/{document_id}", response_model=Document)
    async def get_document(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> Document:
        # No HexIAM type-level gate here; instance-level only.
        try:
            return await document_service.require_document_access(
                principal=principal,
                document_id=document_id,
                required=ResourceAction.READ,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")

    @router.patch("/documents/{document_id}/group", response_model=Document)
    async def move_document_to_group(
        document_id: str,
        group_id: Optional[str] = Query(None, description="Target group ID, or null to remove from group"),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> Document:
        """Move a document to a group or remove it from its current group."""
        try:
            return await document_service.move_document_to_group(
                principal=principal,
                document_id=document_id,
                group_id=group_id,
            )
        except AccessDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")

    @router.patch("/documents/{document_id}/placement", response_model=Document)
    async def place_document(
        document_id: str,
        payload: PlaceDocumentRequest,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> Document:
        try:
            return await document_service.place_document(
                principal=principal,
                document_id=document_id,
                room_id=payload.room_id,
                section_id=payload.section_id,
                position=payload.position,
            )
        except AccessDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            if str(exc) == "section_not_found":
                raise HTTPException(status_code=404, detail="Room section not found")
            raise HTTPException(status_code=404, detail="Document not found")

    @router.delete(
        "/documents/{document_id}",
        status_code=204,
        response_class=Response,
        response_model=None,
    )
    async def delete_document(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> None:
        try:
            await document_service.delete_document(
                principal=principal,
                document_id=document_id,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")
    return router

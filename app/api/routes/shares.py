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
    router = APIRouter(dependencies=[Depends(rate_limit("share_link"))])

    @router.get("/links", response_model=PaginatedResponse[ShareLinkResponse])
    async def list_links(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        link_service: LinkService = Depends(get_link_service),
    ) -> PaginatedResponse[ShareLinkResponse]:
        links = list(await link_service.list_share_links(tenant_id=principal.tenant_id))
        links.sort(key=lambda l: (l.revoked_at is not None, -(l.created_at.timestamp() if l.created_at else 0)))
        total = len(links)
        page = links[offset:offset + limit]
        result: list[ShareLinkResponse] = []
        for link in page:
            token = await link_service.generate_share_token(link)
            result.append(_serialize_link(link, token))
        return PaginatedResponse(items=result, total=total)

    @router.get("/documents/{document_id}/links", response_model=PaginatedResponse[ShareLinkResponse])
    async def list_document_links(
        document_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
        link_service: LinkService = Depends(get_link_service),
    ) -> PaginatedResponse[ShareLinkResponse]:
        try:
            await document_service.require_document_access(
                principal=principal,
                document_id=document_id,
                required=ResourceAction.READ,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")
        links = list(await link_service.list_share_links(
            tenant_id=principal.tenant_id,
            document_id=document_id,
        ))
        links.sort(key=lambda l: (l.revoked_at is not None, -(l.created_at.timestamp() if l.created_at else 0)))
        total = len(links)
        page = links[offset:offset + limit]
        result: list[ShareLinkResponse] = []
        for link in page:
            token = await link_service.generate_share_token(link)
            result.append(_serialize_link(link, token))
        return PaginatedResponse(items=result, total=total)

    @router.post("/documents/{document_id}/links", response_model=ShareLinkResponse)
    async def create_link(
        document_id: str,
        expires_in: int = Query(3600, description="Seconds until link expiry"),
        can_download: bool = Query(False),
        can_print: bool = Query(False),
        require_email: bool = Query(False),
        allowed_emails: Optional[list[str]] = Query(None),
        recipient_email: Optional[str] = Query(None),
        recipient_display_name: Optional[str] = Query(None),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
        link_service: LinkService = Depends(get_link_service),
    ) -> ShareLinkResponse:
        if recipient_display_name and not recipient_email:
            raise HTTPException(status_code=400, detail="recipient_email is required when recipient_display_name is set")
        try:
            await document_service.require_document_access(
                principal=principal,
                document_id=document_id,
                required=ResourceAction.MANAGE,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")
        link = await link_service.create_share_link(
            tenant_id=principal.tenant_id,
            document_id=document_id,
            created_by=principal.user_id,
            expires_in_seconds=expires_in,
            can_download=can_download,
            can_print=can_print,
            require_email=require_email,
            allowed_emails=allowed_emails,
            recipient_email=recipient_email,
            recipient_display_name=recipient_display_name,
        )
        token = await link_service.generate_share_token(link)
        return _serialize_link(link, token)

    @router.post("/links/{link_id}/revoke")
    async def revoke_link(
        link_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
        link_service: LinkService = Depends(get_link_service),
    ) -> None:
        link = await link_service.get_share_link(
            tenant_id=principal.tenant_id, link_id=link_id
        )
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")
        try:
            await document_service.require_document_access(
                principal=principal,
                document_id=link.document_id,
                required=ResourceAction.MANAGE,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")
        await link_service.revoke_share_link(
            tenant_id=principal.tenant_id,
            link_id=link_id,
            revoked_by=principal.user_id,
        )
        return None
    return router

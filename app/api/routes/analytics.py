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
    router = APIRouter(dependencies=[Depends(rate_limit("api_general"))])

    @router.get("/documents/{document_id}/analytics")
    async def document_analytics(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
        analytics_service: AnalyticsService = Depends(get_analytics_service),
    ) -> dict:
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
        metrics = await analytics_service.get_document_metrics(
            tenant_id=principal.tenant_id,
            document_id=document_id,
        )
        return metrics
    return router

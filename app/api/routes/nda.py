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
    router = APIRouter(dependencies=[Depends(rate_limit("nda_create"))])

    # ---- Admin NDA management ----

    async def _require_manage_document(document_service, principal, document_id):
        try:
            await document_service.require_document_access(
                principal=principal, document_id=document_id, required=ResourceAction.MANAGE
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="document_not_found")

    async def _require_manage_group(group_service, principal, group_id):
        try:
            await group_service.get_group(
                principal=principal, group_id=group_id, required=ResourceAction.MANAGE
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="group_not_found")

    async def _set_nda_text(nda_service, *, tenant_id, scope_type, scope_id, created_by, payload):
        try:
            policy = await nda_service.set_policy(
                tenant_id=tenant_id,
                scope_type=scope_type,
                scope_id=scope_id,
                created_by=created_by,
                content_type=NdaContentType.TEXT,
                text_body=payload.text_body,
                title=payload.title,
                require_scroll=payload.require_scroll,
                require_typed_signature=payload.require_typed_signature,
            )
        except NdaError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return _admin_policy_view(policy)

    async def _set_nda_pdf(nda_service, *, tenant_id, scope_type, scope_id, created_by, pdf, title, require_scroll, require_typed_signature):
        content = await pdf.read()
        try:
            policy = await nda_service.set_policy(
                tenant_id=tenant_id,
                scope_type=scope_type,
                scope_id=scope_id,
                created_by=created_by,
                content_type=NdaContentType.PDF,
                pdf_bytes=content,
                title=title,
                require_scroll=require_scroll,
                require_typed_signature=require_typed_signature,
            )
        except NdaError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return _admin_policy_view(policy)

    def _acceptance_view(a) -> NdaAcceptanceRecordView:
        return NdaAcceptanceRecordView(
            id=a.id,
            scope_type=a.scope_type.value,
            scope_id=a.scope_id,
            nda_version=a.nda_version,
            subject_kind=a.subject_kind.value,
            subject_id=a.subject_id,
            presented_email=a.presented_email,
            typed_name=a.typed_name,
            scroll_confirmed=a.scroll_confirmed,
            checkbox_confirmed=a.checkbox_confirmed,
            accepted_at=a.accepted_at,
        )

    # Document-scoped NDA (admin)
    @router.put("/documents/{document_id}/nda", response_model=NdaPolicyAdminView)
    async def set_document_nda(
        document_id: str,
        payload: SetNdaTextRequest,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        document_service: DocumentService = Depends(get_document_service),
    ) -> NdaPolicyAdminView:
        await _require_manage_document(document_service, principal, document_id)
        return await _set_nda_text(
            nda_service, tenant_id=principal.tenant_id, scope_type=NdaScopeType.DOCUMENT,
            scope_id=document_id, created_by=principal.user_id, payload=payload,
        )

    @router.post("/documents/{document_id}/nda/pdf", response_model=NdaPolicyAdminView)
    async def set_document_nda_pdf(
        document_id: str,
        pdf: UploadFile = File(...),
        title: Optional[str] = Form(default=None),
        require_scroll: bool = Form(default=True),
        require_typed_signature: bool = Form(default=True),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        document_service: DocumentService = Depends(get_document_service),
    ) -> NdaPolicyAdminView:
        await _require_manage_document(document_service, principal, document_id)
        return await _set_nda_pdf(
            nda_service, tenant_id=principal.tenant_id, scope_type=NdaScopeType.DOCUMENT,
            scope_id=document_id, created_by=principal.user_id, pdf=pdf, title=title,
            require_scroll=require_scroll, require_typed_signature=require_typed_signature,
        )

    @router.get("/documents/{document_id}/nda", response_model=NdaPolicyAdminView | None)
    async def get_document_nda(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        document_service: DocumentService = Depends(get_document_service),
    ):
        await _require_manage_document(document_service, principal, document_id)
        policy = await nda_service.get_policy(
            tenant_id=principal.tenant_id, scope_type=NdaScopeType.DOCUMENT, scope_id=document_id
        )
        return _admin_policy_view(policy) if policy else None

    @router.delete("/documents/{document_id}/nda", status_code=204, response_class=Response, response_model=None)
    async def delete_document_nda(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        document_service: DocumentService = Depends(get_document_service),
    ) -> None:
        await _require_manage_document(document_service, principal, document_id)
        await nda_service.remove_policy(
            tenant_id=principal.tenant_id, scope_type=NdaScopeType.DOCUMENT, scope_id=document_id
        )
        return None

    @router.get("/documents/{document_id}/nda/acceptances", response_model=list[NdaAcceptanceRecordView])
    async def list_document_nda_acceptances(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        document_service: DocumentService = Depends(get_document_service),
    ) -> list[NdaAcceptanceRecordView]:
        await _require_manage_document(document_service, principal, document_id)
        records = await nda_service.list_acceptances(
            tenant_id=principal.tenant_id, scope_type=NdaScopeType.DOCUMENT, scope_id=document_id
        )
        return [_acceptance_view(a) for a in records]

    # Room-scoped NDA (admin)
    @router.put("/document-groups/{group_id}/nda", response_model=NdaPolicyAdminView)
    async def set_group_nda(
        group_id: str,
        payload: SetNdaTextRequest,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> NdaPolicyAdminView:
        await _require_manage_group(group_service, principal, group_id)
        return await _set_nda_text(
            nda_service, tenant_id=principal.tenant_id, scope_type=NdaScopeType.ROOM,
            scope_id=group_id, created_by=principal.user_id, payload=payload,
        )

    @router.post("/document-groups/{group_id}/nda/pdf", response_model=NdaPolicyAdminView)
    async def set_group_nda_pdf(
        group_id: str,
        pdf: UploadFile = File(...),
        title: Optional[str] = Form(default=None),
        require_scroll: bool = Form(default=True),
        require_typed_signature: bool = Form(default=True),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> NdaPolicyAdminView:
        await _require_manage_group(group_service, principal, group_id)
        return await _set_nda_pdf(
            nda_service, tenant_id=principal.tenant_id, scope_type=NdaScopeType.ROOM,
            scope_id=group_id, created_by=principal.user_id, pdf=pdf, title=title,
            require_scroll=require_scroll, require_typed_signature=require_typed_signature,
        )

    @router.get("/document-groups/{group_id}/nda", response_model=NdaPolicyAdminView | None)
    async def get_group_nda(
        group_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ):
        await _require_manage_group(group_service, principal, group_id)
        policy = await nda_service.get_policy(
            tenant_id=principal.tenant_id, scope_type=NdaScopeType.ROOM, scope_id=group_id
        )
        return _admin_policy_view(policy) if policy else None

    @router.delete("/document-groups/{group_id}/nda", status_code=204, response_class=Response, response_model=None)
    async def delete_group_nda(
        group_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> None:
        await _require_manage_group(group_service, principal, group_id)
        await nda_service.remove_policy(
            tenant_id=principal.tenant_id, scope_type=NdaScopeType.ROOM, scope_id=group_id
        )
        return None

    @router.get("/document-groups/{group_id}/nda/acceptances", response_model=list[NdaAcceptanceRecordView])
    async def list_group_nda_acceptances(
        group_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        nda_service: NdaService = Depends(get_nda_service),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> list[NdaAcceptanceRecordView]:
        await _require_manage_group(group_service, principal, group_id)
        records = await nda_service.list_acceptances(
            tenant_id=principal.tenant_id, scope_type=NdaScopeType.ROOM, scope_id=group_id
        )
        return [_acceptance_view(a) for a in records]
    return router

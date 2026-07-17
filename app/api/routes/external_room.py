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

    @router.get(
        "/external-room/invitations/{token}",
        response_model=ExternalRoomInviteInspectionResponse,
    )
    async def inspect_external_room_invitation(
        token: str,
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> ExternalRoomInviteInspectionResponse:
        try:
            inspection = await external_room_access_service.inspect_invite(invite_token=token)
        except ValueError as exc:
            detail = str(exc)
            if detail in {"grant_not_found", "party_not_found", "group_not_found"}:
                raise HTTPException(status_code=404, detail=detail)
            if detail in {"grant_revoked", "grant_expired"}:
                raise HTTPException(status_code=410, detail=detail)
            raise HTTPException(status_code=400, detail=detail)
        group = inspection["group"]
        grant = inspection["grant"]
        party = inspection["party"]
        return ExternalRoomInviteInspectionResponse(
            room_id=group.id,
            room_name=group.name,
            email=inspection["email"],
            display_name=party.display_name,
            can_download=grant.can_download,
            can_print=grant.can_print,
            expires_at=inspection["expires_at"],
        )

    @router.post(
        "/external-room/invitations/{token}/sessions",
        response_model=ExternalRoomSessionResponse,
    )
    async def create_external_room_session(
        token: str,
        payload: CreateExternalRoomSessionRequest,
        request: Request,
        response: Response,
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> ExternalRoomSessionResponse:
        try:
            inspection = await external_room_access_service.inspect_invite(invite_token=token)
            tokens = await external_room_access_service.create_session_from_invite(
                invite_token=token,
                email=payload.email,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        except ValueError as exc:
            detail = str(exc)
            if detail == "email_required":
                raise HTTPException(status_code=400, detail=detail)
            if detail == "email_not_allowed":
                raise HTTPException(status_code=403, detail=detail)
            if detail in {"grant_revoked", "grant_expired", "party_inactive"}:
                raise HTTPException(status_code=410, detail=detail)
            if detail in {"grant_not_found", "party_not_found", "group_not_found"}:
                raise HTTPException(status_code=404, detail=detail)
            raise HTTPException(status_code=400, detail=detail)
        secure = _secure_cookie(request)
        response.set_cookie(
            EXTERNAL_AUTH_COOKIE,
            tokens.access_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=tokens.expires_in,
        )
        response.set_cookie(
            EXTERNAL_REFRESH_COOKIE,
            tokens.refresh_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=tokens.refresh_expires_in,
        )
        group = inspection["group"]
        party = inspection["party"]
        return ExternalRoomSessionResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            refresh_expires_in=tokens.refresh_expires_in,
            token_type=tokens.token_type,
            room_id=group.id,
            room_name=group.name,
            display_name=party.display_name,
            email=payload.email.strip().lower(),
        )

    @router.post(
        "/external-room/refresh",
        response_model=ExternalRoomSessionResponse,
    )
    async def refresh_external_room_session(
        request: Request,
        response: Response,
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> ExternalRoomSessionResponse:
        refresh_token = request.cookies.get(EXTERNAL_REFRESH_COOKIE)
        if not refresh_token:
            raise HTTPException(status_code=401, detail="Missing external refresh token")
        try:
            tokens = await external_room_access_service.refresh_session(refresh_token=refresh_token)
            principal = await external_room_access_service.authenticate_access_token(
                access_token=tokens.access_token
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        secure = _secure_cookie(request)
        response.set_cookie(
            EXTERNAL_AUTH_COOKIE,
            tokens.access_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=tokens.expires_in,
        )
        response.set_cookie(
            EXTERNAL_REFRESH_COOKIE,
            tokens.refresh_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=tokens.refresh_expires_in,
        )
        group = await external_room_access_service.get_room_group(
            tenant_id=principal.tenant_id,
            room_id=principal.room_id,
        )
        return ExternalRoomSessionResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            refresh_expires_in=tokens.refresh_expires_in,
            token_type=tokens.token_type,
            room_id=principal.room_id,
            room_name=group.name if group else principal.room_id,
            display_name=principal.display_name,
            email=principal.email,
        )

    @router.post(
        "/external-room/logout",
        status_code=204,
        response_class=Response,
        response_model=None,
    )
    async def logout_external_room_session(
        response: Response,
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> None:
        await external_room_access_service.close_session(principal=principal)
        response.delete_cookie(EXTERNAL_AUTH_COOKIE, path="/")
        response.delete_cookie(EXTERNAL_REFRESH_COOKIE, path="/")
        return None

    @router.get(
        "/external-room/current",
        response_model=ExternalRoomContextResponse,
    )
    async def get_external_room_context(
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        group_service: DocumentGroupService = Depends(get_document_group_service),
        nda_service: NdaService = Depends(get_nda_service),
    ) -> ExternalRoomContextResponse:
        try:
            group = await group_service.get_group(
                principal=principal.as_tenant_principal(),
                group_id=principal.room_id,
                required=ResourceAction.READ,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        subject = NdaService.subject_from_room_principal(principal)
        policy, accepted = await nda_service.room_policy_status(
            tenant_id=principal.tenant_id, room_id=principal.room_id, subject=subject
        )
        return ExternalRoomContextResponse(
            room_id=group.id,
            room_name=group.name,
            display_name=principal.display_name,
            email=principal.email,
            can_download=principal.can_download,
            can_print=principal.can_print,
            nda=_build_nda_status(policy, accepted),
        )

    @router.get("/external-room/current/documents", response_model=list[Document])
    async def list_external_room_documents(
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        group_service: DocumentGroupService = Depends(get_document_group_service),
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
        nda_service: NdaService = Depends(get_nda_service),
    ) -> list[Document]:
        # Room-level NDA blocks the whole room, including the document list.
        subject = NdaService.subject_from_room_principal(principal)
        await nda_service.require_room_accepted(
            tenant_id=principal.tenant_id, room_id=principal.room_id, subject=subject
        )
        try:
            docs = await group_service.list_group_documents(
                principal=principal.as_tenant_principal(),
                group_id=principal.room_id,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        await external_room_access_service.record_document_list(principal=principal)
        return list(docs)

    @router.get("/external-room/current/nda", response_model=list[NdaStatusResponse])
    async def get_external_room_nda(
        document_id: str | None = Query(default=None),
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        nda_service: NdaService = Depends(get_nda_service),
        document_service: DocumentService = Depends(get_document_service),
    ) -> list[NdaStatusResponse]:
        """Applicable NDA statuses (with text content). Room-scope by default; when
        ``document_id`` is given, returns the room + that document's NDAs."""
        subject = NdaService.subject_from_room_principal(principal)
        statuses: list[NdaStatusResponse] = []
        room_policy, room_accepted = await nda_service.room_policy_status(
            tenant_id=principal.tenant_id, room_id=principal.room_id, subject=subject
        )
        if room_policy is not None:
            statuses.append(_build_nda_status(room_policy, room_accepted))
        if document_id:
            document = await document_service.get_document(
                tenant_id=principal.tenant_id, document_id=document_id
            )
            if document and document.room_id == principal.room_id:
                doc_policy = await nda_service.get_policy(
                    tenant_id=principal.tenant_id, scope_type=NdaScopeType.DOCUMENT, scope_id=document.id
                )
                if doc_policy is not None:
                    _, doc_accepted = await nda_service.policy_status(policy=doc_policy, subject=subject)
                    statuses.append(_build_nda_status(doc_policy, doc_accepted))
        return statuses

    @router.get("/external-room/current/nda/pdf")
    async def get_external_room_nda_pdf(
        scope_type: str = Query(...),
        scope_id: str = Query(...),
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        nda_service: NdaService = Depends(get_nda_service),
    ) -> StreamingResponse:
        policy = await _load_recipient_nda_policy(
            nda_service, tenant_id=principal.tenant_id, room_id=principal.room_id,
            scope_type=scope_type, scope_id=scope_id,
        )
        pdf = await nda_service.get_pdf_bytes(policy=policy)
        return StreamingResponse(
            iter([pdf]),
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=nda.pdf", "Cache-Control": "private, no-store"},
        )

    @router.post("/external-room/current/nda/accept", response_model=NdaAcceptResponse)
    async def accept_external_room_nda(
        payload: NdaAcceptRequest,
        request: Request,
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        nda_service: NdaService = Depends(get_nda_service),
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> NdaAcceptResponse:
        policy = await _load_recipient_nda_policy(
            nda_service, tenant_id=principal.tenant_id, room_id=principal.room_id,
            scope_type=payload.scope_type, scope_id=payload.scope_id,
        )
        subject = NdaService.subject_from_room_principal(principal)
        try:
            acceptance = await nda_service.accept(
                policy=policy,
                subject=subject,
                typed_name=payload.typed_name,
                scroll_confirmed=payload.scroll_confirmed,
                checkbox_confirmed=payload.checkbox_confirmed,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        except NdaError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await external_room_access_service.record_nda_accepted(
            principal=principal,
            document_id=policy.scope_id if policy.scope_type == NdaScopeType.DOCUMENT else None,
        )
        return NdaAcceptResponse(
            accepted=True,
            scope_type=acceptance.scope_type.value,
            scope_id=acceptance.scope_id,
            version=acceptance.nda_version,
            accepted_at=acceptance.accepted_at,
        )


    @router.get(
        "/external-room/current/documents/{document_id}/download",
        response_model=DownloadUrlResponse,
    )
    async def get_external_room_document_download(
        document_id: str,
        expires_in: int = Query(default=900, ge=60, le=3600),
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        document_service: DocumentService = Depends(get_document_service),
        upload_service: UploadService = Depends(get_upload_service),
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> DownloadUrlResponse:
        try:
            document = await document_service.require_document_access(
                principal=principal.as_tenant_principal(),
                document_id=document_id,
                required=ResourceAction.EXPORT,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")
        await external_room_access_service.record_document_download(
            principal=principal,
            document_id=document_id,
        )
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

    @router.post(
        "/external-room/current/documents/{document_id}/sessions",
        response_model=ExternalRoomDocumentSessionResponse,
    )
    async def create_external_room_document_session(
        document_id: str,
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        external_room_viewer_service: ExternalRoomViewerService = Depends(get_external_room_viewer_service),
    ) -> ExternalRoomDocumentSessionResponse:
        try:
            delivery = await external_room_viewer_service.create_view_session(
                principal=principal,
                document_id=document_id,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found")
        return _serialize_external_room_document_session(delivery)

    @router.get(
        "/external-room/view-sessions/{session_id}",
        response_model=ExternalRoomDocumentSessionResponse,
    )
    async def get_external_room_document_session(
        session_id: str,
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        external_room_viewer_service: ExternalRoomViewerService = Depends(get_external_room_viewer_service),
    ) -> ExternalRoomDocumentSessionResponse:
        try:
            delivery = await external_room_viewer_service.describe_view_session(
                principal=principal,
                session_id=session_id,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError as exc:
            detail = str(exc)
            status_code = 404 if detail == "session_not_found" else 404
            raise HTTPException(status_code=status_code, detail=detail)
        return _serialize_external_room_document_session(delivery)

    @router.get("/external-room/view-sessions/{session_id}/content")
    async def stream_external_room_view_content(
        session_id: str,
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        external_room_viewer_service: ExternalRoomViewerService = Depends(get_external_room_viewer_service),
    ) -> StreamingResponse:
        try:
            streamed = await external_room_viewer_service.stream_document(
                principal=principal,
                session_id=session_id,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except DocumentProcessingError as exc:
            detail = str(exc)
            if detail == "inline_view_not_supported":
                status_code = 415
            elif detail == "page_image_view_required":
                status_code = 409
            else:
                status_code = 422
            raise HTTPException(status_code=status_code, detail=detail)

        response = StreamingResponse(
            _stream_bytes(streamed.content),
            media_type=streamed.media_type,
        )
        return _apply_viewer_headers(
            response,
            filename=streamed.filename,
            disposition="inline",
        )

    @router.get("/external-room/view-sessions/{session_id}/pages/{page_number}")
    async def stream_external_room_view_page_image(
        session_id: str,
        page_number: int,
        width: int = Query(1400, ge=400, le=2200),
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        external_room_viewer_service: ExternalRoomViewerService = Depends(get_external_room_viewer_service),
    ) -> StreamingResponse:
        try:
            rendered = await external_room_viewer_service.render_document_page(
                principal=principal,
                session_id=session_id,
                page_number=page_number,
                render_width=width,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except DocumentProcessingError as exc:
            detail = str(exc)
            if detail == "page_out_of_range":
                status_code = 404
            elif detail == "invalid_page_number":
                status_code = 400
            elif detail == "page_image_view_not_supported":
                status_code = 415
            elif detail == "inline_view_backend_unavailable":
                status_code = 503
            else:
                status_code = 422
            raise HTTPException(status_code=status_code, detail=detail)

        response = StreamingResponse(
            _stream_bytes(rendered.content),
            media_type=rendered.media_type,
        )
        return _apply_viewer_headers(
            response,
            filename=_build_page_image_filename(f"{session_id}.pdf", page_number),
            disposition="inline",
        )

    @router.get("/external-room/view-sessions/{session_id}/download")
    async def download_external_room_view_content(
        session_id: str,
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        external_room_viewer_service: ExternalRoomViewerService = Depends(get_external_room_viewer_service),
    ) -> StreamingResponse:
        try:
            streamed = await external_room_viewer_service.download_document(
                principal=principal,
                session_id=session_id,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError as exc:
            detail = str(exc)
            if detail == "download_not_allowed":
                raise HTTPException(status_code=403, detail="Downloads are disabled for this room grant")
            raise HTTPException(status_code=404, detail=detail)

        response = StreamingResponse(
            _stream_bytes(streamed.content),
            media_type=streamed.media_type,
        )
        return _apply_viewer_headers(
            response,
            filename=streamed.filename,
            disposition="attachment",
        )

    @router.post("/external-room/view-sessions/{session_id}/close")
    async def close_external_room_view_session(
        session_id: str,
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        external_room_viewer_service: ExternalRoomViewerService = Depends(get_external_room_viewer_service),
    ) -> dict:
        try:
            await external_room_viewer_service.close_view_session(
                principal=principal,
                session_id=session_id,
            )
        except (AccessDenied, ValueError):
            pass
        return {"status": "closed"}

    @router.post("/external-room/view-sessions/{session_id}/page-view")
    async def record_external_room_page_view(
        session_id: str,
        page_number: int = Query(..., ge=1, description="Page number being viewed"),
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        external_room_viewer_service: ExternalRoomViewerService = Depends(get_external_room_viewer_service),
    ) -> dict:
        try:
            await external_room_viewer_service.record_page_view(
                principal=principal,
                session_id=session_id,
                page_number=page_number,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"status": "ok"}
    return router

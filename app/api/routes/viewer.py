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
from app.core.watermark_identity import pseudonymous_watermark
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

    # ---- Share-link recipient NDA endpoints ----

    @router.get("/view-sessions/{session_id}/nda", response_model=list[NdaStatusResponse])
    async def get_share_nda(
        session_id: str,
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> list[NdaStatusResponse]:
        try:
            _resolved, applicable, outstanding = await viewer_service.nda_status(session_id=session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        outstanding_ids = {p.id for p in outstanding}
        return [_build_nda_status(p, p.id not in outstanding_ids) for p in applicable]

    @router.get("/view-sessions/{session_id}/nda/pdf")
    async def get_share_nda_pdf(
        session_id: str,
        scope_type: str = Query(...),
        scope_id: str = Query(...),
        viewer_service: ViewerService = Depends(get_viewer_service),
        nda_service: NdaService = Depends(get_nda_service),
    ) -> StreamingResponse:
        try:
            resolved, applicable, _ = await viewer_service.nda_status(session_id=session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        policy = next(
            (p for p in applicable if p.scope_type.value == scope_type and p.scope_id == scope_id),
            None,
        )
        if policy is None:
            raise HTTPException(status_code=404, detail="nda_not_found")
        pdf = await nda_service.get_pdf_bytes(policy=policy)
        return StreamingResponse(
            iter([pdf]),
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=nda.pdf", "Cache-Control": "private, no-store"},
        )

    @router.post("/view-sessions/{session_id}/nda/accept", response_model=NdaAcceptResponse)
    async def accept_share_nda(
        session_id: str,
        payload: NdaAcceptRequest,
        request: Request,
        viewer_service: ViewerService = Depends(get_viewer_service),
        nda_service: NdaService = Depends(get_nda_service),
    ) -> NdaAcceptResponse:
        try:
            resolved, applicable, _ = await viewer_service.nda_status(session_id=session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        policy = next(
            (p for p in applicable if p.scope_type.value == payload.scope_type and p.scope_id == payload.scope_id),
            None,
        )
        if policy is None:
            raise HTTPException(status_code=404, detail="nda_not_found")
        subject = NdaService.subject_from_view_session(resolved)
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
        return NdaAcceptResponse(
            accepted=True,
            scope_type=acceptance.scope_type.value,
            scope_id=acceptance.scope_id,
            version=acceptance.nda_version,
            accepted_at=acceptance.accepted_at,
        )


    @router.get("/view/{token}", response_model=ShareLinkInspectionResponse)
    async def inspect_view_document(
        token: str,
        share_auth: ShareTokenDependency = Depends(get_share_auth),
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> ShareLinkInspectionResponse:
        claims: ShareTokenClaims = share_auth(token)
        try:
            inspection = await viewer_service.inspect_share_token(
                tenant_id=claims.tenant_id,
                document_id=claims.document_id,
                link_id=claims.link_id,
            )
        except ValueError:
            raise HTTPException(status_code=404, detail="Share link or document not found")
        document = inspection["document"]
        link = inspection["link"]
        return ShareLinkInspectionResponse(
            tenant=claims.tenant_id,
            document=claims.document_id,
            document_name=document.name,
            mime_type=document.mime_type,
            size=document.size,
            link=claims.link_id,
            permissions=claims.permissions,
            require_email=claims.require_email,
            allowed_emails=list(link.allowed_emails or []),
            revoked=inspection["revoked"],
            expired=inspection["expired"],
        )

    @router.post("/view/{token}/sessions", response_model=CreateViewSessionResponse)
    async def create_view_session(
        token: str,
        payload: CreateViewSessionRequest,
        request: Request,
        share_auth: ShareTokenDependency = Depends(get_share_auth),
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> CreateViewSessionResponse:
        claims: ShareTokenClaims = share_auth(token)
        try:
            session = await viewer_service.create_view_session(
                tenant_id=claims.tenant_id,
                document_id=claims.document_id,
                link_id=claims.link_id,
                email=payload.email,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            delivery = await viewer_service.describe_view_session_delivery(
                tenant_id=claims.tenant_id,
                session_id=session.id,
            )
        except ValueError as exc:
            detail = str(exc)
            if detail == "email_required":
                raise HTTPException(status_code=400, detail="Email is required for this share link")
            if detail == "email_not_allowed":
                raise HTTPException(status_code=403, detail="Your email is not authorized to view this document")
            if detail == "revoked":
                raise HTTPException(status_code=403, detail="This share link has been revoked")
            if detail == "expired":
                raise HTTPException(status_code=410, detail="This share link has expired")
            raise HTTPException(status_code=404, detail="Share link or document not found")

        return CreateViewSessionResponse(
            session_id=session.id,
            tenant_id=claims.tenant_id,
            document_id=claims.document_id,
            document_name=delivery.resolved.document_name,
            mime_type=delivery.resolved.mime_type,
            size=delivery.resolved.size,
            link_id=claims.link_id,
            permissions=claims.permissions,
            content_path=f"/api/v1/view-sessions/{session.id}/content",
            download_path=(
                f"/api/v1/view-sessions/{session.id}/download"
                if delivery.resolved.can_download
                else None
            ),
            events_path=f"/api/v1/view-sessions/{session.id}/events",
            watermark_text=pseudonymous_watermark(
                session.id,
                claims.link_id,
                payload.email,
            ),
            inline_view_supported=delivery.view_policy.inline_view_supported,
            view_kind=delivery.view_policy.view_kind,
            view_reason=delivery.view_policy.reason,
            page_count=delivery.pdf_preview.page_count if delivery.pdf_preview else None,
            page_image_path_template=(
                f"/api/v1/view-sessions/{session.id}/pages/{{page}}"
                if delivery.pdf_preview
                else None
            ),
        )

    @router.get("/view-sessions/{session_id}/content")
    async def stream_view_content(
        session_id: str,
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> StreamingResponse:
        try:
            streamed = await viewer_service.stream_document(session_id=session_id)
        except ValueError as exc:
            detail = str(exc)
            status_code = 404
            if detail in {"revoked", "session_closed"}:
                status_code = 403
            elif detail == "expired":
                status_code = 410
            raise HTTPException(status_code=status_code, detail=detail)
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

    @router.get("/view-sessions/{session_id}/pages/{page_number}")
    async def stream_view_page_image(
        session_id: str,
        page_number: int,
        width: int = Query(1400, ge=400, le=2200),
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> StreamingResponse:
        try:
            rendered = await viewer_service.render_document_page(
                session_id=session_id,
                page_number=page_number,
                render_width=width,
            )
        except ValueError as exc:
            detail = str(exc)
            status_code = 404
            if detail in {"revoked", "session_closed"}:
                status_code = 403
            elif detail == "expired":
                status_code = 410
            raise HTTPException(status_code=status_code, detail=detail)
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

    @router.get("/view-sessions/{session_id}/download")
    async def download_view_content(
        session_id: str,
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> StreamingResponse:
        try:
            resolved = await viewer_service.resolve_view_session(session_id=session_id)
            active = await viewer_service.ensure_active_session(
                tenant_id=resolved.session.tenant_id,
                session_id=session_id,
            )
            if not active.can_download:
                await viewer_service.record_download_attempt(
                    tenant_id=active.session.tenant_id,
                    session_id=session_id,
                    blocked=True,
                )
                raise HTTPException(status_code=403, detail="Downloads are disabled for this share link")
            await viewer_service.record_download_attempt(
                tenant_id=active.session.tenant_id,
                session_id=session_id,
                blocked=False,
            )
            streamed = await viewer_service.download_document(
                tenant_id=active.session.tenant_id,
                session_id=session_id,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            detail = str(exc)
            status_code = 404
            if detail in {"revoked", "session_closed"}:
                status_code = 403
            elif detail == "expired":
                status_code = 410
            raise HTTPException(status_code=status_code, detail=detail)

        response = StreamingResponse(
            _stream_bytes(streamed.content),
            media_type=streamed.media_type,
        )
        return _apply_viewer_headers(
            response,
            filename=streamed.filename,
            disposition="attachment",
        )

    @router.post("/view-sessions/{session_id}/page-view")
    async def record_page_view(
        session_id: str,
        page_number: int = Query(..., ge=1, description="Page number being viewed"),
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> dict:
        try:
            resolved = await viewer_service.resolve_view_session(session_id=session_id)
            await viewer_service.record_page_view(
                tenant_id=resolved.session.tenant_id,
                session_id=session_id,
                page_number=page_number,
            )
        except ValueError as exc:
            detail = str(exc)
            status_code = 404
            if detail in {"revoked", "session_closed"}:
                status_code = 403
            elif detail == "expired":
                status_code = 410
            raise HTTPException(status_code=status_code, detail=detail)
        return {"status": "ok"}

    @router.post("/view-sessions/{session_id}/close")
    async def close_view_session(
        session_id: str,
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> dict:
        try:
            resolved = await viewer_service.resolve_view_session(session_id=session_id)
            await viewer_service.close_session(
                tenant_id=resolved.session.tenant_id,
                session_id=session_id,
            )
        except ValueError:
            pass
        return {"status": "closed"}

    @router.get("/view-sessions/{session_id}/events")
    async def stream_viewer_events(
        session_id: str,
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> StreamingResponse:
        async def event_generator():
            while True:
                try:
                    resolved = await viewer_service.resolve_view_session(session_id=session_id)
                except ValueError:
                    yield 'event: status\ndata: {"status":"not_found"}\n\n'
                    break

                status = "active"
                if resolved.session.ended_at is not None:
                    status = "closed"
                elif resolved.revoked:
                    status = "revoked"
                elif resolved.expired:
                    status = "expired"

                yield f'event: status\ndata: {{"status":"{status}"}}\n\n'
                if status != "active":
                    break
                try:
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    break

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return router

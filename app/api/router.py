from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies.services import (
    get_analytics_service,
    get_document_service,
    get_link_service,
    get_share_auth,
    get_viewer_service,
)
from app.auth import ShareTokenClaims, TenantPrincipal
from app.auth.share_token_auth import ShareTokenDependency
from app.auth.tenant_auth import get_tenant_auth
from app.domain import Document, ShareLink
from app.schemas.share import ShareLinkResponse
from app.schemas.viewer import (
    CreateViewSessionRequest,
    CreateViewSessionResponse,
    ShareLinkInspectionResponse,
    ViewerHeartbeatRequest,
)
from app.services import AnalyticsService, DocumentService, LinkService, ViewerService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize_link(link: ShareLink, token: str) -> ShareLinkResponse:
    return ShareLinkResponse(
        id=link.id,
        tenant_id=link.tenant_id,
        document_id=link.document_id,
        jti=link.jti,
        expires_at=link.expires_at,
        can_download=link.can_download,
        can_print=link.can_print,
        require_email=link.require_email,
        allowed_emails=list(link.allowed_emails or []),
        revoked_at=link.revoked_at,
        created_at=link.created_at,
        created_by=link.created_by,
        share_token=token,
        share_path=f"/view/{token}",
    )


def api_router() -> APIRouter:
    router = APIRouter()

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

    @router.get("/documents", response_model=list[Document])
    async def list_documents(
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> list[Document]:
        docs = await document_service.list_documents(tenant_id=principal.tenant_id)
        return list(docs)

    @router.get("/documents/{document_id}", response_model=Document)
    async def get_document(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> Document:
        doc = await document_service.get_document(
            tenant_id=principal.tenant_id,
            document_id=document_id,
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc

    @router.get("/links", response_model=list[ShareLinkResponse])
    async def list_links(
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        link_service: LinkService = Depends(get_link_service),
    ) -> list[ShareLinkResponse]:
        links = await link_service.list_share_links(tenant_id=principal.tenant_id)
        result: list[ShareLinkResponse] = []
        for link in links:
            token = await link_service.generate_share_token(link)
            result.append(_serialize_link(link, token))
        return result

    @router.get("/documents/{document_id}/links", response_model=list[ShareLinkResponse])
    async def list_document_links(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
        link_service: LinkService = Depends(get_link_service),
    ) -> list[ShareLinkResponse]:
        doc = await document_service.get_document(
            tenant_id=principal.tenant_id,
            document_id=document_id,
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        links = await link_service.list_share_links(
            tenant_id=principal.tenant_id,
            document_id=document_id,
        )
        result: list[ShareLinkResponse] = []
        for link in links:
            token = await link_service.generate_share_token(link)
            result.append(_serialize_link(link, token))
        return result

    @router.post("/documents/{document_id}/links", response_model=ShareLinkResponse)
    async def create_link(
        document_id: str,
        expires_in: int = Query(3600, description="Seconds until link expiry"),
        can_download: bool = Query(False),
        can_print: bool = Query(False),
        require_email: bool = Query(False),
        allowed_emails: Optional[list[str]] = Query(None),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
        link_service: LinkService = Depends(get_link_service),
    ) -> ShareLinkResponse:
        if not await document_service.get_document(
            tenant_id=principal.tenant_id,
            document_id=document_id,
        ):
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
        )
        token = await link_service.generate_share_token(link)
        return _serialize_link(link, token)

    @router.post("/links/{link_id}/revoke")
    async def revoke_link(
        link_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        link_service: LinkService = Depends(get_link_service),
    ) -> None:
        await link_service.revoke_share_link(
            tenant_id=principal.tenant_id,
            link_id=link_id,
            revoked_by=principal.user_id,
        )
        return None

    @router.get("/documents/{document_id}/analytics")
    async def document_analytics(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        analytics_service: AnalyticsService = Depends(get_analytics_service),
    ) -> dict:
        metrics = await analytics_service.get_document_metrics(
            tenant_id=principal.tenant_id,
            document_id=document_id,
        )
        return metrics

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
            resolved = await viewer_service.ensure_active_session(
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

        watermark = payload.email or claims.link_id
        return CreateViewSessionResponse(
            session_id=session.id,
            tenant_id=claims.tenant_id,
            document_id=claims.document_id,
            document_name=resolved.document_name,
            mime_type=resolved.mime_type,
            size=resolved.size,
            link_id=claims.link_id,
            permissions=claims.permissions,
            content_path=f"/api/v1/view-sessions/{session.id}/content",
            download_path=(
                f"/api/v1/view-sessions/{session.id}/download"
                if resolved.can_download
                else None
            ),
            events_path=f"/api/v1/view-sessions/{session.id}/events",
            watermark_text=f"HexShare • {watermark}",
        )

    @router.get("/view-sessions/{session_id}/content")
    async def stream_view_content(
        session_id: str,
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> StreamingResponse:
        try:
            resolved = await viewer_service.resolve_view_session(session_id=session_id)
            active = await viewer_service.ensure_active_session(
                tenant_id=resolved.session.tenant_id,
                session_id=session_id,
            )
            signed_url_pair = await viewer_service.get_signed_inline_url(
                tenant_id=active.session.tenant_id,
                session_id=session_id,
            )
            _, signed_url = signed_url_pair
        except ValueError as exc:
            detail = str(exc)
            status_code = 404
            if detail in {"revoked", "session_closed"}:
                status_code = 403
            elif detail == "expired":
                status_code = 410
            raise HTTPException(status_code=status_code, detail=detail)

        response = StreamingResponse(
            viewer_service.stream_via_signed_url(url=signed_url),
            media_type=active.mime_type or "application/octet-stream",
        )
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Robots-Tag"] = "noindex, noarchive, nosnippet"
        response.headers["Content-Disposition"] = f'inline; filename="{active.document_name}"'
        return response

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
            _, signed_url = await viewer_service.get_signed_download_url(
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
            viewer_service.stream_via_signed_url(url=signed_url),
            media_type=active.mime_type or "application/octet-stream",
        )
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Disposition"] = f'attachment; filename="{active.document_name}"'
        return response

    @router.post("/view-sessions/{session_id}/heartbeat")
    async def viewer_heartbeat(
        session_id: str,
        payload: ViewerHeartbeatRequest,
        viewer_service: ViewerService = Depends(get_viewer_service),
    ) -> dict:
        try:
            resolved = await viewer_service.resolve_view_session(session_id=session_id)
            await viewer_service.record_heartbeat(
                tenant_id=resolved.session.tenant_id,
                session_id=session_id,
                page_number=payload.page_number,
                duration_ms=payload.duration_ms,
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
                await asyncio.sleep(2)

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

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from app.api.dependencies.services import (
    get_analytics_service,
    get_document_group_service,
    get_document_service,
    get_iam_policy,
    get_link_service,
    get_share_auth,
    get_viewer_service,
)
from app.auth import ShareTokenClaims, TenantPrincipal
from app.auth.share_token_auth import ShareTokenDependency
from app.auth.tenant_auth import get_tenant_auth
from app.core.authz import ResourceAction
from app.domain import Document, DocumentGroup, ShareLink
from app.ports.access_control import AccessDenied
from app.schemas.share import ShareLinkResponse
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
    LinkService,
    ViewerService,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _stream_bytes(content: bytes):
    yield content


def _apply_viewer_headers(response: StreamingResponse, *, filename: str, disposition: str) -> StreamingResponse:
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Robots-Tag"] = "noindex, noarchive, nosnippet"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response


def _build_page_image_filename(filename: str, page_number: int) -> str:
    path = Path(filename)
    stem = path.stem or "document"
    return f"{stem}-page-{page_number}.png"


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
        docs = await document_service.list_accessible_documents(principal=principal)
        return list(docs)

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


    @router.get("/document-groups", response_model=list[DocumentGroup])
    async def list_document_groups(
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> list[DocumentGroup]:
        groups = await group_service.list_user_groups(principal=principal)
        return list(groups)

    @router.post("/document-groups", response_model=DocumentGroup)
    async def create_document_group(
        name: str = Query(..., description="Group name"),
        description: Optional[str] = Query(None),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> DocumentGroup:
        try:
            return await group_service.create_group(
                principal=principal, name=name, description=description
            )
        except AccessDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @router.get("/document-groups/{group_id}", response_model=DocumentGroup)
    async def get_document_group(
        group_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> DocumentGroup:
        try:
            return await group_service.get_group(principal=principal, group_id=group_id)
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")

    @router.patch("/document-groups/{group_id}", response_model=DocumentGroup)
    async def update_document_group(
        group_id: str,
        name: Optional[str] = Query(None),
        description: Optional[str] = Query(None),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> DocumentGroup:
        try:
            return await group_service.update_group(
                principal=principal,
                group_id=group_id,
                name=name,
                description=description,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")

    @router.delete(
        "/document-groups/{group_id}",
        status_code=204,
        response_class=Response,
        response_model=None,
    )
    async def delete_document_group(
        group_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> None:
        try:
            await group_service.delete_group(principal=principal, group_id=group_id)
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")
        return None

    @router.get("/document-groups/{group_id}/documents", response_model=list[Document])
    async def list_document_group_documents(
        group_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> list[Document]:
        try:
            docs = await group_service.list_group_documents(
                principal=principal, group_id=group_id
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        return list(docs)

    @router.post("/document-groups/{group_id}/documents", response_model=Document)
    async def create_document_in_group(
        group_id: str,
        name: str = Query(..., description="Name of the document"),
        mime_type: str = Query(..., description="MIME type"),
        size: int = Query(..., description="Size in bytes"),
        storage_key: str = Query(..., description="Key in object storage"),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> Document:
        # Verify caller has WRITE on the group; also ensures group exists.
        try:
            await group_service.get_group(
                principal=principal, group_id=group_id, required=ResourceAction.WRITE
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")
        return await document_service.create_document(
            tenant_id=principal.tenant_id,
            name=name,
            mime_type=mime_type,
            size=size,
            storage_key=storage_key,
            created_by=principal.user_id,
            room_id=group_id,
        )

    @router.post("/document-groups/{group_id}/members", status_code=201)
    async def add_group_member(
        group_id: str,
        user_id: str = Query(..., description="User ID to add as member"),
        role: str = Query("member", description="Role: 'member' or 'owner'"),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> dict:
        """Add a member to a group. Only owners can add members."""
        try:
            await group_service.add_member(
                principal=principal,
                group_id=group_id,
                member_user_id=user_id,
                role=role,
            )
        except AccessDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")
        return {"status": "ok", "user_id": user_id, "role": role}

    @router.delete(
        "/document-groups/{group_id}/members/{user_id}",
        status_code=204,
        response_class=Response,
        response_model=None,
    )
    async def remove_group_member(
        group_id: str,
        user_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> None:
        """Remove a member from a group. Only owners can remove members."""
        try:
            await group_service.remove_member(
                principal=principal,
                group_id=group_id,
                member_user_id=user_id,
            )
        except AccessDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")
        return None

    @router.get("/workspace/users")
    async def list_workspace_users(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=100, description="Page size"),
        search: Optional[str] = Query(None, description="Search filter"),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        iam_policy = Depends(get_iam_policy),
    ) -> dict:
        """List users in the workspace, excluding the current user."""
        from app.ports.iam_policy import IAMPolicyError
        try:
            result = await iam_policy.list_tenant_users(
                tenant_id=principal.tenant_id,
                page=page,
                page_size=page_size,
                search=search,
            )
            # Filter out the current user
            users = result.get("users", result.get("items", []))
            users = [u for u in users if u.get("id") != principal.user_id and u.get("user_id") != principal.user_id]
            return {
                "users": users,
                "total": result.get("total", len(users)),
                "page": page,
                "page_size": page_size,
            }
        except IAMPolicyError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to list users: {exc}")

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

        watermark = payload.email or claims.link_id
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
            watermark_text=f"HexShare - {watermark}",
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

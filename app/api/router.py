from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from app.api.dependencies.services import (
    get_analytics_service,
    get_document_group_service,
    get_document_service,
    get_external_room_access_service,
    get_external_room_viewer_service,
    get_iam_policy,
    get_link_service,
    get_share_auth,
    get_upload_service,
    get_viewer_service,
)
from app.auth import ShareTokenClaims, TenantPrincipal
from app.auth.external_room_auth import get_external_room_principal
from app.auth.share_token_auth import ShareTokenDependency
from app.auth.tenant_auth import get_tenant_auth
from app.core.authz import EXTERNAL_AUTH_COOKIE, EXTERNAL_REFRESH_COOKIE, ResourceAction
from app.domain import Document, DocumentGroup, ShareLink
from app.ports.access_control import AccessDenied
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
    UploadService,
    ViewerService,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _stream_bytes(content: bytes):
    yield content


def _secure_cookie(request: Request) -> bool:
    public = (os.getenv("HEXSHARE_PUBLIC_URL") or "").strip()
    if public.startswith("https://"):
        return True
    return request.url.scheme == "https"


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
        access_mode=link.access_mode.value,
        bound_email_normalized=link.bound_email_normalized,
        revoked_at=link.revoked_at,
        created_at=link.created_at,
        created_by=link.created_by,
        share_token=token,
        share_path=f"/view/{token}",
    )


def external_room_document_watermark(principal: ExternalRoomPrincipal) -> str:
    identifier = principal.email
    if principal.display_name:
        identifier = f"{principal.display_name} <{principal.email}>"
    return f"HexShare - {identifier}"


def _serialize_external_room_document_session(
    delivery: ExternalRoomDocumentSessionDelivery,
) -> ExternalRoomDocumentSessionResponse:
    resolved = delivery.resolved
    permissions = {
        "read": True,
        "download": resolved.can_download,
        "print": resolved.can_print,
    }
    return ExternalRoomDocumentSessionResponse(
        session_id=resolved.session_id,
        tenant_id=resolved.principal.tenant_id,
        room_id=resolved.principal.room_id,
        document_id=resolved.document_id,
        document_name=resolved.document_name,
        mime_type=resolved.mime_type,
        size=resolved.size,
        permissions=permissions,
        content_path=f"/api/v1/external-room/view-sessions/{resolved.session_id}/content",
        download_path=(
            f"/api/v1/external-room/view-sessions/{resolved.session_id}/download"
            if resolved.can_download
            else None
        ),
        watermark_text=external_room_document_watermark(resolved.principal),
        inline_view_supported=delivery.view_policy.inline_view_supported,
        view_kind=delivery.view_policy.view_kind,
        view_reason=delivery.view_policy.reason,
        page_count=delivery.pdf_preview.page_count if delivery.pdf_preview else None,
        page_image_path_template=(
            f"/api/v1/external-room/view-sessions/{resolved.session_id}/pages/{{page}}"
            if delivery.pdf_preview
            else None
        ),
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

    @router.get("/documents", response_model=PaginatedResponse[Document])
    async def list_documents(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        document_service: DocumentService = Depends(get_document_service),
    ) -> PaginatedResponse[Document]:
        docs = list(await document_service.list_accessible_documents(principal=principal))
        total = len(docs)
        return PaginatedResponse(items=docs[offset:offset + limit], total=total)

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


    @router.get("/document-groups", response_model=PaginatedResponse[DocumentGroup])
    async def list_document_groups(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
    ) -> PaginatedResponse[DocumentGroup]:
        groups = list(await group_service.list_user_groups(principal=principal))
        total = len(groups)
        return PaginatedResponse(items=groups[offset:offset + limit], total=total)

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

    @router.post(
        "/document-groups/{group_id}/external-access",
        response_model=ProvisionExternalRoomAccessResponse,
    )
    async def provision_external_room_access(
        group_id: str,
        recipient_email: str = Query(...),
        recipient_display_name: Optional[str] = Query(None),
        can_download: bool = Query(False),
        can_print: bool = Query(False),
        expires_in: Optional[int] = Query(None, ge=60),
        invite_expires_in: int = Query(60 * 60 * 24 * 7, ge=300),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> ProvisionExternalRoomAccessResponse:
        try:
            await group_service.get_group(
                principal=principal,
                group_id=group_id,
                required=ResourceAction.MANAGE,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")
        provisioned = await external_room_access_service.provision_room_access(
            principal=principal,
            room_id=group_id,
            recipient_email=recipient_email,
            recipient_display_name=recipient_display_name,
            can_download=can_download,
            can_print=can_print,
            expires_in_seconds=expires_in,
            invite_expires_in_seconds=invite_expires_in,
        )
        return ProvisionExternalRoomAccessResponse(
            external_party_id=provisioned.party.id,
            display_name=provisioned.party.display_name,
            email=recipient_email.strip().lower(),
            grant_id=provisioned.grant.id,
            room_id=group_id,
            invite_token=provisioned.invite_token,
            invite_path=f"/external-room/invitations/{provisioned.invite_token}",
            invite_expires_at=provisioned.invite_expires_at,
            can_download=provisioned.grant.can_download,
            can_print=provisioned.grant.can_print,
        )

    @router.get(
        "/document-groups/{group_id}/external-access",
        response_model=list[ExternalRoomGrantResponse],
    )
    async def list_external_room_access(
        group_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> list[ExternalRoomGrantResponse]:
        try:
            await group_service.get_group(
                principal=principal,
                group_id=group_id,
                required=ResourceAction.MANAGE,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")
        items = await external_room_access_service.list_room_access(
            tenant_id=principal.tenant_id,
            room_id=group_id,
        )
        return [ExternalRoomGrantResponse(**item) for item in items]

    @router.delete(
        "/document-groups/{group_id}/external-access/{grant_id}",
        status_code=204,
        response_class=Response,
        response_model=None,
    )
    async def revoke_external_room_access(
        group_id: str,
        grant_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        group_service: DocumentGroupService = Depends(get_document_group_service),
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> None:
        try:
            await group_service.get_group(
                principal=principal,
                group_id=group_id,
                required=ResourceAction.MANAGE,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        except ValueError:
            raise HTTPException(status_code=404, detail="Group not found")
        try:
            await external_room_access_service.revoke_room_access(
                tenant_id=principal.tenant_id,
                grant_id=grant_id,
                room_id=group_id,
            )
        except ValueError:
            raise HTTPException(status_code=404, detail="Grant not found")
        return None

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
    ) -> ExternalRoomContextResponse:
        try:
            group = await group_service.get_group(
                principal=principal.as_tenant_principal(),
                group_id=principal.room_id,
                required=ResourceAction.READ,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        return ExternalRoomContextResponse(
            room_id=group.id,
            room_name=group.name,
            display_name=principal.display_name,
            email=principal.email,
            can_download=principal.can_download,
            can_print=principal.can_print,
        )

    @router.get("/external-room/current/documents", response_model=list[Document])
    async def list_external_room_documents(
        principal: ExternalRoomPrincipal = Depends(get_external_room_principal),
        group_service: DocumentGroupService = Depends(get_document_group_service),
        external_room_access_service: ExternalRoomAccessService = Depends(get_external_room_access_service),
    ) -> list[Document]:
        try:
            docs = await group_service.list_group_documents(
                principal=principal.as_tenant_principal(),
                group_id=principal.room_id,
            )
        except AccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden")
        await external_room_access_service.record_document_list(principal=principal)
        return list(docs)

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

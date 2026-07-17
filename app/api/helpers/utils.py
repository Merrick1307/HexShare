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


def _build_nda_status(policy, accepted: bool, *, include_text: bool = True) -> NdaStatusResponse:
    if policy is None:
        return NdaStatusResponse(required=False, accepted=True)
    return NdaStatusResponse(
        required=True,
        accepted=accepted,
        policy=NdaPolicyView(
            scope_type=policy.scope_type.value,
            scope_id=policy.scope_id,
            version=policy.version,
            title=policy.title,
            content_type=policy.content_type.value,
            require_scroll=policy.require_scroll,
            require_typed_signature=policy.require_typed_signature,
        ),
        text_body=policy.text_body if (include_text and policy.content_type == NdaContentType.TEXT) else None,
        pdf_available=policy.content_type == NdaContentType.PDF,
    )


async def _load_recipient_nda_policy(nda_service, *, tenant_id, room_id, scope_type, scope_id):
    """Fetch an NDA policy a room recipient is allowed to read (room-scope must be
    their own room; document-scope is allowed within that room)."""
    if scope_type not in ("room", "document"):
        raise HTTPException(status_code=400, detail="invalid_scope_type")
    if scope_type == "room" and scope_id != room_id:
        raise HTTPException(status_code=404, detail="nda_not_found")
    policy = await nda_service.get_policy(
        tenant_id=tenant_id, scope_type=NdaScopeType(scope_type), scope_id=scope_id
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="nda_not_found")
    return policy


def _admin_policy_view(policy) -> NdaPolicyAdminView:
    return NdaPolicyAdminView(
        scope_type=policy.scope_type.value,
        scope_id=policy.scope_id,
        version=policy.version,
        title=policy.title,
        content_type=policy.content_type.value,
        require_scroll=policy.require_scroll,
        require_typed_signature=policy.require_typed_signature,
        active=policy.active,
        has_pdf=policy.content_type == NdaContentType.PDF,
        updated_at=policy.updated_at,
    )


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

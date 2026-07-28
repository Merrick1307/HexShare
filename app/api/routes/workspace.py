from __future__ import annotations

import asyncio
import inspect
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
    ProductEventRequest,
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

    # ---- Workspace dashboards (summary / activity / NDA compliance) ----

    async def _owner_scoped(method, *, principal: TenantPrincipal, **kwargs):
        """Use hosted individual filtering without changing OSS team semantics."""
        if "created_by" in inspect.signature(method).parameters:
            kwargs["created_by"] = principal.user_id
        return await method(**kwargs)

    @router.get("/workspace/summary", response_model=WorkspaceSummaryResponse)
    async def workspace_summary(
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        storage=Depends(get_storage),
    ) -> WorkspaceSummaryResponse:
        data = await _owner_scoped(
            storage.get_workspace_summary,
            principal=principal,
            tenant_id=principal.tenant_id,
        )
        data = dict(data)
        data["onboarding_complete"] = (
            int(data.get("documents") or 0) > 0
            and int(data.get("groups") or 0) > 0
            and (
                int(data.get("active_links") or 0) > 0
                or int(data.get("external_recipients") or 0) > 0
            )
            and int(data.get("document_opens") or 0) > 0
        )
        return WorkspaceSummaryResponse(**data)

    @router.post("/workspace/product-events", status_code=204)
    async def record_product_event(
        body: ProductEventRequest,
        request: Request,
        principal: TenantPrincipal = Depends(get_tenant_auth()),
    ) -> Response:
        # Deliberately accept only a fixed event and step vocabulary. Customer
        # document names, recipient emails, and file contents cannot enter this
        # analytics channel.
        await request.app.state.event_bus.publish_event(
            principal.tenant_id,
            body.event_name,
            {
                "owner_user_id": principal.user_id,
                "step": body.step,
            },
        )
        return Response(status_code=204)

    @router.get("/activity", response_model=list[ActivityItemResponse])
    async def workspace_activity(
        limit: int = Query(default=50, ge=1, le=200),
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        storage=Depends(get_storage),
    ) -> list[ActivityItemResponse]:
        tenant_id = principal.tenant_id
        view_events = list(
            await _owner_scoped(
                storage.list_recent_view_events,
                principal=principal,
                tenant_id=tenant_id,
                limit=limit,
            )
        )
        room_events = list(
            await _owner_scoped(
                storage.list_recent_external_room_events,
                principal=principal,
                tenant_id=tenant_id,
                limit=limit,
            )
        )

        documents = list(
            await _owner_scoped(
                storage.list_documents,
                principal=principal,
                tenant_id=tenant_id,
            )
        )
        doc_names = {d.id: d.name for d in documents}
        room_ids = {e.room_id for e in room_events if e.room_id}
        groups = (
            list(await storage.list_document_groups_by_ids(tenant_id=tenant_id, group_ids=room_ids))
            if room_ids
            else []
        )
        room_names = {g.id: g.name for g in groups}
        sessions = list(await storage.list_external_room_sessions(tenant_id=tenant_id))
        session_email = {s.id: s.presented_email for s in sessions}

        def _etype(value) -> str:
            return value.value if hasattr(value, "value") else str(value)

        items: list[ActivityItemResponse] = []
        for event in view_events:
            items.append(
                ActivityItemResponse(
                    timestamp=event.timestamp,
                    source="share",
                    event_type=_etype(event.event_type),
                    document_id=event.document_id,
                    document_name=doc_names.get(event.document_id),
                    page_number=event.page_number,
                    actor=None,
                )
            )
        for event in room_events:
            items.append(
                ActivityItemResponse(
                    timestamp=event.timestamp,
                    source="room",
                    event_type=_etype(event.event_type),
                    document_id=event.document_id,
                    document_name=doc_names.get(event.document_id) if event.document_id else None,
                    room_id=event.room_id,
                    room_name=room_names.get(event.room_id),
                    page_number=event.page_number,
                    actor=session_email.get(event.external_room_session_id),
                )
            )
        items.sort(key=lambda item: item.timestamp, reverse=True)
        return items[:limit]

    @router.get("/nda/policies", response_model=list[NdaPolicySummaryResponse])
    async def workspace_nda_policies(
        principal: TenantPrincipal = Depends(get_tenant_auth()),
        storage=Depends(get_storage),
    ) -> list[NdaPolicySummaryResponse]:
        tenant_id = principal.tenant_id
        policies = list(
            await _owner_scoped(
                storage.list_nda_policies,
                principal=principal,
                tenant_id=tenant_id,
            )
        )
        documents = list(
            await _owner_scoped(
                storage.list_documents,
                principal=principal,
                tenant_id=tenant_id,
            )
        )
        doc_names = {d.id: d.name for d in documents}
        room_ids = {p.scope_id for p in policies if p.scope_type == NdaScopeType.ROOM}
        groups = (
            list(await storage.list_document_groups_by_ids(tenant_id=tenant_id, group_ids=room_ids))
            if room_ids
            else []
        )
        room_names = {g.id: g.name for g in groups}

        out: list[NdaPolicySummaryResponse] = []
        for policy in policies:
            acceptances = list(
                await storage.list_nda_acceptances(
                    tenant_id=tenant_id, scope_type=policy.scope_type.value, scope_id=policy.scope_id
                )
            )
            count = sum(1 for a in acceptances if a.nda_version == policy.version)
            name = (
                room_names.get(policy.scope_id)
                if policy.scope_type == NdaScopeType.ROOM
                else doc_names.get(policy.scope_id)
            )
            out.append(
                NdaPolicySummaryResponse(
                    scope_type=policy.scope_type.value,
                    scope_id=policy.scope_id,
                    scope_name=name,
                    version=policy.version,
                    title=policy.title,
                    content_type=policy.content_type.value,
                    require_scroll=policy.require_scroll,
                    require_typed_signature=policy.require_typed_signature,
                    acceptance_count=count,
                    updated_at=policy.updated_at,
                )
            )
        return out


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
    return router

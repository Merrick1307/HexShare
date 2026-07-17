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
    return router

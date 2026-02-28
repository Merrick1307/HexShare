from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies.services import (get_document_service, get_link_service,
                                           get_analytics_service, get_tenant_auth, get_share_auth)
from app.domain import Document, ShareLink
from app.services import DocumentService, LinkService, AnalyticsService
from app.auth import TenantPrincipal, ShareTokenClaims


def api_router() -> APIRouter:
    router = APIRouter()

    @router.post("/documents", response_model=Document)
    async def create_document(
        name: str = Query(..., description="Name of the document"),
        mime_type: str = Query(..., description="MIME type"),
        size: int = Query(..., description="Size in bytes"),
        storage_key: str = Query(..., description="Key in object storage"),
        principal: TenantPrincipal = Depends(get_tenant_auth),
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
            principal: TenantPrincipal = Depends(get_tenant_auth),
            document_service: DocumentService = Depends(get_document_service)
    ) -> list[Document]:
        docs = await document_service.list_documents(tenant_id=principal.tenant_id)
        return list(docs)

    @router.get("/documents/{document_id}", response_model=Document)
    async def get_document(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth),
        document_service: DocumentService = Depends(get_document_service),
    ) -> Document:
        doc = await document_service.get_document(
            tenant_id=principal.tenant_id, document_id=document_id
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc

    @router.post("/documents/{document_id}/links", response_model=ShareLink)
    async def create_link(
        document_id: str,
        expires_in: int = Query(3600, description="Seconds until link expiry"),
        can_download: bool = Query(False),
        can_print: bool = Query(False),
        require_email: bool = Query(False),
        allowed_emails: Optional[list[str]] = Query(None),
        principal: TenantPrincipal = Depends(get_tenant_auth),
        document_service: DocumentService = Depends(get_document_service),
        link_service: LinkService = Depends(get_link_service),
    ) -> ShareLink:
        if not await document_service.get_document(
            tenant_id=principal.tenant_id, document_id=document_id
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
        return link

    @router.post("/links/{link_id}/revoke")
    async def revoke_link(
        link_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth),
        link_service: LinkService = Depends(get_link_service),
    ) -> None:
        await link_service.revoke_share_link(
            tenant_id=principal.tenant_id, link_id=link_id, revoked_by=principal.user_id
        )
        return None

    @router.get("/documents/{document_id}/analytics")
    async def document_analytics(
        document_id: str,
        principal: TenantPrincipal = Depends(get_tenant_auth),
        analytics_service: AnalyticsService = Depends(get_analytics_service),
    ) -> dict:
        metrics = await analytics_service.get_document_metrics(
            tenant_id=principal.tenant_id, document_id=document_id
        )
        return metrics

    @router.get("/view/{token}")
    async def view_document(claims: ShareTokenClaims = Depends(get_share_auth)) -> dict:
        """Example endpoint demonstrating share token usage.

        In a real application this would return an HTML/JS viewer that
        loads the document.  Here we return the claims for inspection.
        """
        return {
            "tenant": claims.tenant_id,
            "document": claims.document_id,
            "link": claims.link_id,
            "permissions": claims.permissions,
        }

    return router

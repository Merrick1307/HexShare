"""
Document service implementation.

This service contains the business logic for managing documents.  It
interacts with the storage port to persist document metadata and uses
the event bus to emit audit events when necessary.  It does not handle
uploading of raw file bytes – that responsibility belongs to the
storage adapter.  Instead, the service records the location of the
uploaded file and stores metadata about it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from app.auth.tenant_auth import TenantPrincipal
from app.core.authz import ResourceAction
from app.domain import Document, DocumentPermission
from app.ports import EventBusPort
from app.ports.access_control import AccessDenied
from app.ports.storage_port import StoragePort


# Permissions granted to the creator of an ungrouped document.
_OWNER_BITMASK = int(
    ResourceAction.READ
    | ResourceAction.WRITE
    | ResourceAction.DELETE
    | ResourceAction.MANAGE
    | ResourceAction.EXPORT
)


class DocumentService:
    """Service responsible for document lifecycle operations."""

    def __init__(self, storage: StoragePort, event_bus: EventBusPort) -> None:
        self._storage = storage
        self._event_bus = event_bus

    async def create_document(
        self,
        *,
        tenant_id: str,
        name: str,
        mime_type: str,
        size: int,
        storage_key: str,
        created_by: str,
        document_id: str | None = None,
        room_id: str | None = None,
    ) -> Document:
        """Create a new document record.

        The raw file is assumed already uploaded to object storage and
        addressable via ``storage_key``.  When ``room_id`` is ``None`` the
        creator is automatically granted full permissions on the document
        via the instance-level ACL.  Grouped documents (``room_id`` set)
        inherit access from the room's IAM policy, so no permission row
        is created.
        """
        doc_id = document_id or self._storage.generate_id("doc")
        now = datetime.utcnow()
        document = Document(
            id=doc_id,
            tenant_id=tenant_id,
            name=name,
            mime_type=mime_type,
            size=size,
            storage_key=storage_key,
            created_at=now,
            created_by=created_by,
            room_id=room_id,
        )
        await self._storage.save_document(document)

        if room_id is None:
            await self._storage.save_document_permission(
                DocumentPermission(
                    document_id=doc_id,
                    tenant_id=tenant_id,
                    user_id=created_by,
                    permissions=_OWNER_BITMASK,
                    granted_by=created_by,
                    granted_at=now,
                )
            )

        await self._event_bus.publish_event(
            tenant_id,
            "document.created",
            {
                "document_id": doc_id,
                "name": name,
                "mime_type": mime_type,
                "size": size,
                "created_by": created_by,
                "room_id": room_id,
            },
        )
        return document

    async def get_document(self, *, tenant_id: str, document_id: str) -> Document | None:
        """Retrieve a document by ID without enforcing access checks."""
        return await self._storage.get_document(tenant_id=tenant_id, document_id=document_id)

    async def list_documents(self, *, tenant_id: str) -> Iterable[Document]:
        """List every document in a tenant (no access filtering)."""
        return await self._storage.list_documents(tenant_id=tenant_id)

    @staticmethod
    def _principal_has_room_permission(
        principal: TenantPrincipal, room_id: str, required: ResourceAction
    ) -> bool:
        mask = int(principal.policy.get(room_id, 0) or 0)
        return bool(mask & int(required))

    async def require_document_access(
        self,
        *,
        principal: TenantPrincipal,
        document_id: str,
        required: ResourceAction,
    ) -> Document:
        """Resolve a document and enforce instance-level access.

        For ungrouped documents this consults ``document_permissions``;
        for grouped documents it checks the principal's JWT policy for
        the parent room's bitmask.  Raises :class:`AccessDenied` if the
        principal lacks the requested permission.  Raises ``ValueError``
        with ``"document_not_found"`` when the document does not exist.
        """
        doc = await self._storage.get_document(
            tenant_id=principal.tenant_id, document_id=document_id
        )
        if not doc:
            raise ValueError("document_not_found")

        if doc.room_id is None:
            perm = await self._storage.get_document_permission(
                tenant_id=principal.tenant_id,
                document_id=document_id,
                user_id=principal.user_id,
            )
            if not perm or not (perm.permissions & int(required)):
                raise AccessDenied("insufficient_document_permission")
        else:
            if not self._principal_has_room_permission(principal, doc.room_id, required):
                raise AccessDenied("insufficient_room_permission")
        return doc

    async def list_accessible_documents(
        self, *, principal: TenantPrincipal, required: ResourceAction = ResourceAction.READ
    ) -> Iterable[Document]:
        """List ungrouped documents the principal has ``required`` on."""
        return await self._storage.list_ungrouped_documents_by_permission(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            required_permission=int(required),
        )

    async def delete_document(
        self, *, principal: TenantPrincipal, document_id: str
    ) -> None:
        """Delete a document. Requires MANAGE permission."""
        await self.require_document_access(
            principal=principal,
            document_id=document_id,
            required=ResourceAction.MANAGE,
        )
        await self._storage.delete_document(
            tenant_id=principal.tenant_id,
            document_id=document_id,
        )

    async def grant_document_permission(
        self,
        *,
        tenant_id: str,
        document_id: str,
        user_id: str,
        permissions: int,
        granted_by: str,
    ) -> DocumentPermission:
        """Grant or update a user's permissions on an ungrouped document."""
        record = DocumentPermission(
            document_id=document_id,
            tenant_id=tenant_id,
            user_id=user_id,
            permissions=int(permissions),
            granted_by=granted_by,
            granted_at=datetime.utcnow(),
        )
        await self._storage.save_document_permission(record)
        return record

    async def revoke_document_permission(
        self, *, tenant_id: str, document_id: str, user_id: str
    ) -> None:
        await self._storage.revoke_document_permission(
            tenant_id=tenant_id, document_id=document_id, user_id=user_id
        )

    async def move_document_to_group(
        self,
        *,
        principal: TenantPrincipal,
        document_id: str,
        group_id: Optional[str],
    ) -> Document:
        """Move a document to a group or remove it from its current group.

        User must have MANAGE permission on the document (or its current group)
        and WRITE permission on the target group (if any).
        """
        doc = await self.require_document_access(
            principal=principal,
            document_id=document_id,
            required=ResourceAction.MANAGE,
        )

        if group_id:
            if not self._principal_has_room_permission(principal, group_id, ResourceAction.WRITE):
                raise AccessDenied("insufficient_target_group_permission")

        updated = await self._storage.update_document_room(
            tenant_id=principal.tenant_id,
            document_id=document_id,
            room_id=group_id,
        )
        if not updated:
            raise ValueError("document_not_found")
        return updated

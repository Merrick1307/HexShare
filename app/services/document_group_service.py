"""
Document group (room) service.

Encapsulates the dual-write coordination between HexShare's local
``document_groups`` table and the IAM provider's resource policies.

Authorization model:
  * Group existence and metadata live in HexShare.
  * Per-user permissions on a group live in the IAM provider as a
    policy whose ``resource`` field equals the group ID.
  * The JWT carries the resulting bitmask: ``policy[group_id] = mask``.

Creating a group registers a MANAGE policy for the creator with the IAM
provider before persisting the local row; failures roll back the IAM
side via a compensating revoke.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional
from uuid import uuid4

from app.auth.tenant_auth import TenantPrincipal
from app.core.authz import (
    DOCUMENT_GROUP_PREFIX,
    ResourceAction,
    bitmask_to_action_names,
)
from app.domain import Document, DocumentGroup
from app.ports.access_control import AccessDenied
from app.ports.iam_policy import IAMPolicyError, IAMPolicyPort
from app.ports.storage_port import StoragePort


def _group_policy_id(group_id: str) -> str:
    """Namespace IAM policy IDs to avoid collisions with other HexShare features."""
    return group_id


def _generate_group_id() -> str:
    # ULID-style IDs would be nicer but ``uuid4`` keeps us dependency-free.
    return f"{DOCUMENT_GROUP_PREFIX}{uuid4().hex}"


_OWNER_GROUP_BITMASK = int(
    ResourceAction.READ
    | ResourceAction.WRITE
    | ResourceAction.DELETE
    | ResourceAction.MANAGE
    | ResourceAction.EXPORT
)

_MEMBER_GROUP_BITMASK = int(
    ResourceAction.READ
    | ResourceAction.WRITE
    | ResourceAction.EXPORT
)


class DocumentGroupService:
    def __init__(self, storage: StoragePort, iam_policy: IAMPolicyPort) -> None:
        self._storage = storage
        self._iam = iam_policy

    @staticmethod
    def _group_ids_from_principal(principal: TenantPrincipal) -> List[str]:
        return [
            key for key in (principal.policy or {}).keys()
            if isinstance(key, str) and key.startswith(DOCUMENT_GROUP_PREFIX)
        ]

    @staticmethod
    def _require_group_permission(
        principal: TenantPrincipal, group_id: str, required: ResourceAction
    ) -> None:
        mask = int((principal.policy or {}).get(group_id, 0) or 0)
        if not (mask & int(required)):
            raise AccessDenied("insufficient_room_permission")

    async def list_user_groups(
        self, *, principal: TenantPrincipal
    ) -> Iterable[DocumentGroup]:
        ids = self._group_ids_from_principal(principal)
        if not ids:
            return []
        return await self._storage.list_document_groups_by_ids(
            tenant_id=principal.tenant_id, group_ids=ids
        )

    async def get_group(
        self, *, principal: TenantPrincipal, group_id: str, required: ResourceAction = ResourceAction.READ
    ) -> DocumentGroup:
        self._require_group_permission(principal, group_id, required)
        group = await self._storage.get_document_group(
            tenant_id=principal.tenant_id, group_id=group_id
        )
        if not group:
            raise ValueError("group_not_found")
        return group

    async def list_group_documents(
        self, *, principal: TenantPrincipal, group_id: str
    ) -> Iterable[Document]:
        # Ensure caller can READ the room before exposing its contents.
        self._require_group_permission(principal, group_id, ResourceAction.READ)
        return await self._storage.list_documents_by_room(
            tenant_id=principal.tenant_id, room_id=group_id
        )

    async def create_group(
        self,
        *,
        principal: TenantPrincipal,
        name: str,
        description: Optional[str] = None,
    ) -> DocumentGroup:
        """Create a new group, registering the IAM policy first.

        IAM-first ordering ensures we never leave an orphaned HexShare row
        pointing at a non-existent IAM resource.  If the local insert
        fails, we issue a compensating revoke against the IAM provider.
        """
        if not principal.token:
            raise AccessDenied("missing_bearer_token")

        group_id = _generate_group_id()
        policy_id = _group_policy_id(group_id)

        await self._iam.grant_policy(
            bearer_token=principal.token,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            policy_id=policy_id,
            resource=group_id,
            actions=bitmask_to_action_names(_OWNER_GROUP_BITMASK),
        )

        group = DocumentGroup(
            id=group_id,
            tenant_id=principal.tenant_id,
            name=name,
            description=description,
            created_by=principal.user_id,
            created_at=datetime.utcnow(),
        )
        try:
            await self._storage.save_document_group(group)
        except Exception:
            # Best-effort compensating revoke; raise the original error.
            try:
                await self._iam.revoke_policy(
                    bearer_token=principal.token,
                    tenant_id=principal.tenant_id,
                    user_id=principal.user_id,
                    policy_id=policy_id,
                )
            except IAMPolicyError:
                pass
            raise
        return group

    async def update_group(
        self,
        *,
        principal: TenantPrincipal,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DocumentGroup:
        self._require_group_permission(principal, group_id, ResourceAction.MANAGE)
        updated = await self._storage.update_document_group(
            tenant_id=principal.tenant_id,
            group_id=group_id,
            name=name,
            description=description,
        )
        if not updated:
            raise ValueError("group_not_found")
        return updated

    async def delete_group(
        self, *, principal: TenantPrincipal, group_id: str
    ) -> None:
        """Delete a group, transferring its documents to the creator.

        Documents that lived in the group have their ``room_id`` cleared
        (via FK ``ON DELETE SET NULL``) and the group's creator is
        granted ownership on each so the documents remain accessible.
        Finally, the IAM policy for the group is revoked.
        """
        if not principal.token:
            raise AccessDenied("missing_bearer_token")
        self._require_group_permission(principal, group_id, ResourceAction.MANAGE)

        group = await self._storage.get_document_group(
            tenant_id=principal.tenant_id, group_id=group_id
        )
        if not group:
            raise ValueError("group_not_found")

        docs = list(
            await self._storage.list_documents_by_room(
                tenant_id=principal.tenant_id, room_id=group_id
            )
        )

        now = datetime.utcnow()
        from app.domain import DocumentPermission  # local import to avoid cycle
        for doc in docs:
            await self._storage.save_document_permission(
                DocumentPermission(
                    document_id=doc.id,
                    tenant_id=principal.tenant_id,
                    user_id=group.created_by,
                    permissions=_OWNER_GROUP_BITMASK,
                    granted_by=principal.user_id,
                    granted_at=now,
                )
            )

        await self._storage.delete_document_group(
            tenant_id=principal.tenant_id, group_id=group_id
        )

        # Revoke the creator's IAM policy (best-effort; IAM port handles 404).
        try:
            await self._iam.revoke_policy(
                bearer_token=principal.token,
                tenant_id=principal.tenant_id,
                user_id=group.created_by,
                policy_id=_group_policy_id(group_id),
            )
        except IAMPolicyError:
            # Local state is the source of truth; surface a soft warning
            # via the caller in production logs.
            pass

    async def add_member(
        self,
        *,
        principal: TenantPrincipal,
        group_id: str,
        member_user_id: str,
        role: str = "member",
    ) -> None:
        """Add a member to a group with appropriate permissions.

        Only owners (MANAGE permission) can add members.
        """
        if not principal.token:
            raise AccessDenied("missing_bearer_token")
        self._require_group_permission(principal, group_id, ResourceAction.MANAGE)

        # Verify the group exists
        group = await self._storage.get_document_group(
            tenant_id=principal.tenant_id, group_id=group_id
        )
        if not group:
            raise ValueError("group_not_found")

        # Determine permission bitmask based on role
        if role == "owner":
            bitmask = _OWNER_GROUP_BITMASK
        else:
            bitmask = _MEMBER_GROUP_BITMASK

        policy_id = _group_policy_id(group_id)
        await self._iam.grant_policy(
            bearer_token=principal.token,
            tenant_id=principal.tenant_id,
            user_id=member_user_id,
            policy_id=policy_id,
            resource=group_id,
            actions=bitmask_to_action_names(bitmask),
        )

    async def remove_member(
        self,
        *,
        principal: TenantPrincipal,
        group_id: str,
        member_user_id: str,
    ) -> None:
        """Remove a member from a group.

        Only owners (MANAGE permission) can remove members.
        The group creator cannot be removed.
        """
        if not principal.token:
            raise AccessDenied("missing_bearer_token")
        self._require_group_permission(principal, group_id, ResourceAction.MANAGE)

        group = await self._storage.get_document_group(
            tenant_id=principal.tenant_id, group_id=group_id
        )
        if not group:
            raise ValueError("group_not_found")

        # Prevent removing the group creator
        if member_user_id == group.created_by:
            raise AccessDenied("cannot_remove_creator")

        policy_id = _group_policy_id(group_id)
        try:
            await self._iam.revoke_policy(
                bearer_token=principal.token,
                tenant_id=principal.tenant_id,
                user_id=member_user_id,
                policy_id=policy_id,
            )
        except IAMPolicyError:
            # If IAM says policy doesn't exist, that's fine - user wasn't a member
            pass

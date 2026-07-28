"""NDA gate service.

Owns NDA policy lifecycle (attach/update/remove an NDA to a room or a document),
the acceptance check that gates content delivery, and recording acceptances.

Enforcement rule: to open a document, every *applicable* active NDA must be
accepted at its current version — that means the room's NDA (if the document is
in a room) AND the document's own NDA (if it has one). Bumping a policy's version
invalidates prior acceptances and forces re-acceptance.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain import (
    Document,
    NdaAcceptance,
    NdaContentType,
    NdaPolicy,
    NdaScopeType,
    NdaSubjectKind,
)
from app.ports.object_storage_port import ObjectStoragePort, ObjectWriteRequest
from app.ports.storage_port import StoragePort
from app.ports import EventBusPort


class NdaError(ValueError):
    """Domain error for NDA operations (maps to a 400 at the API layer)."""


class NdaAcceptanceRequired(Exception):
    """Raised when content is requested before required NDAs are accepted.

    Deliberately NOT a ValueError so it propagates past endpoints' generic
    ``except ValueError`` blocks to a dedicated 403 handler.
    """

    detail = "nda_acceptance_required"


@dataclass(frozen=True)
class NdaSubject:
    """The identity accepting (or gated by) an NDA."""

    subject_kind: NdaSubjectKind
    subject_id: str
    external_party_id: str | None = None
    presented_email: str | None = None
    session_id: str | None = None


class NdaService:
    def __init__(self, *, storage: StoragePort, object_storage: ObjectStoragePort, event_bus: EventBusPort | None = None) -> None:
        self._storage = storage
        self._object_storage = object_storage
        self._event_bus = event_bus

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _hash(value: str | None) -> str | None:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    # -- subject resolution ---------------------------------------------------------

    @staticmethod
    def subject_from_room_principal(principal) -> NdaSubject:
        return NdaSubject(
            subject_kind=NdaSubjectKind.EXTERNAL_PARTY,
            subject_id=principal.external_party_id,
            external_party_id=principal.external_party_id,
            presented_email=principal.email,
            session_id=principal.session_id,
        )

    @staticmethod
    def subject_from_view_session(resolved) -> NdaSubject:
        session = resolved.session
        party_id = session.external_party_id
        email = resolved.email
        if party_id:
            return NdaSubject(
                subject_kind=NdaSubjectKind.EXTERNAL_PARTY,
                subject_id=party_id,
                external_party_id=party_id,
                presented_email=email,
                session_id=session.id,
            )
        if email:
            return NdaSubject(
                subject_kind=NdaSubjectKind.VISITOR_EMAIL,
                subject_id=email,
                presented_email=email,
                session_id=session.id,
            )
        return NdaSubject(
            subject_kind=NdaSubjectKind.VISITOR_SESSION,
            subject_id=session.id,
            session_id=session.id,
        )

    # -- policy lifecycle (admin) ---------------------------------------------------

    def _text_object_key(self, *, tenant_id: str, scope_type: str, scope_id: str, version: int) -> str:
        return f"nda/{tenant_id}/{scope_type}/{scope_id}/v{version}.txt"

    def _pdf_object_key(self, *, tenant_id: str, scope_type: str, scope_id: str, version: int) -> str:
        return f"nda/{tenant_id}/{scope_type}/{scope_id}/v{version}.pdf"

    async def set_policy(
        self,
        *,
        tenant_id: str,
        scope_type: NdaScopeType,
        scope_id: str,
        created_by: str,
        content_type: NdaContentType,
        text_body: str | None = None,
        pdf_bytes: bytes | None = None,
        title: str | None = None,
        require_scroll: bool = True,
        require_typed_signature: bool = True,
    ) -> NdaPolicy:
        existing = await self._storage.get_nda_policy(
            tenant_id=tenant_id,
            scope_type=scope_type.value,
            scope_id=scope_id,
            active_only=False,
        )
        now = self._now()

        if content_type == NdaContentType.TEXT:
            if not (text_body and text_body.strip()):
                raise NdaError("nda_text_required")
        else:
            if not pdf_bytes:
                raise NdaError("nda_pdf_required")

        # Bump version whenever content materially changes (or first creation),
        # which forces recipients to re-accept.
        content_changed = (
            existing is None
            or existing.content_type != content_type
            or (content_type == NdaContentType.TEXT and (existing.text_body or "") != (text_body or ""))
            or (content_type == NdaContentType.PDF and pdf_bytes is not None)
        )
        version = (existing.version + 1) if (existing and content_changed) else (existing.version if existing else 1)

        text_storage_key = existing.text_storage_key if existing else None
        pdf_storage_key = existing.pdf_storage_key if existing else None

        if content_type == NdaContentType.TEXT:
            text_storage_key = self._text_object_key(
                tenant_id=tenant_id, scope_type=scope_type.value, scope_id=scope_id, version=version
            )
            await self._object_storage.write_object(
                ObjectWriteRequest(
                    object_key=text_storage_key,
                    content=text_body.encode("utf-8"),
                    content_type="text/plain; charset=utf-8",
                )
            )
            pdf_storage_key = None
        else:
            pdf_storage_key = self._pdf_object_key(
                tenant_id=tenant_id, scope_type=scope_type.value, scope_id=scope_id, version=version
            )
            await self._object_storage.write_object(
                ObjectWriteRequest(
                    object_key=pdf_storage_key,
                    content=pdf_bytes,
                    content_type="application/pdf",
                )
            )
            text_body = None
            text_storage_key = None

        policy = NdaPolicy(
            id=existing.id if existing else self._storage.generate_id("nda"),
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            version=version,
            title=title,
            content_type=content_type,
            text_body=text_body,
            text_storage_key=text_storage_key,
            pdf_storage_key=pdf_storage_key,
            require_scroll=require_scroll,
            require_typed_signature=require_typed_signature,
            active=True,
            created_by=existing.created_by if existing else created_by,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        await self._storage.save_nda_policy(policy)
        return policy

    async def remove_policy(self, *, tenant_id: str, scope_type: NdaScopeType, scope_id: str) -> None:
        await self._storage.deactivate_nda_policy(
            tenant_id=tenant_id, scope_type=scope_type.value, scope_id=scope_id
        )

    async def get_policy(
        self, *, tenant_id: str, scope_type: NdaScopeType, scope_id: str, active_only: bool = True
    ) -> NdaPolicy | None:
        return await self._storage.get_nda_policy(
            tenant_id=tenant_id, scope_type=scope_type.value, scope_id=scope_id, active_only=active_only
        )

    async def get_pdf_bytes(self, *, policy: NdaPolicy) -> bytes:
        if policy.content_type != NdaContentType.PDF or not policy.pdf_storage_key:
            raise NdaError("nda_not_pdf")
        return await self._object_storage.read_object(object_key=policy.pdf_storage_key)

    async def list_acceptances(
        self, *, tenant_id: str, scope_type: NdaScopeType, scope_id: str
    ) -> list[NdaAcceptance]:
        return list(
            await self._storage.list_nda_acceptances(
                tenant_id=tenant_id, scope_type=scope_type.value, scope_id=scope_id
            )
        )

    # -- gate (recipient) -----------------------------------------------------------

    async def applicable_policies(self, *, document: Document) -> list[NdaPolicy]:
        """Active NDAs that apply to a document: its room's, then its own."""
        policies: list[NdaPolicy] = []
        if document.room_id:
            room_policy = await self._storage.get_nda_policy(
                tenant_id=document.tenant_id, scope_type="room", scope_id=document.room_id
            )
            if room_policy:
                policies.append(room_policy)
        doc_policy = await self._storage.get_nda_policy(
            tenant_id=document.tenant_id, scope_type="document", scope_id=document.id
        )
        if doc_policy:
            policies.append(doc_policy)
        return policies

    async def _is_accepted(self, *, policy: NdaPolicy, subject: NdaSubject) -> bool:
        record = await self._storage.get_nda_acceptance(
            tenant_id=policy.tenant_id,
            scope_type=policy.scope_type.value,
            scope_id=policy.scope_id,
            nda_version=policy.version,
            subject_kind=subject.subject_kind.value,
            subject_id=subject.subject_id,
        )
        return record is not None

    async def outstanding_policies(
        self, *, document: Document, subject: NdaSubject
    ) -> list[NdaPolicy]:
        outstanding: list[NdaPolicy] = []
        for policy in await self.applicable_policies(document=document):
            if not await self._is_accepted(policy=policy, subject=subject):
                outstanding.append(policy)
        return outstanding

    async def require_all_accepted(self, *, document: Document, subject: NdaSubject) -> None:
        if await self.outstanding_policies(document=document, subject=subject):
            raise NdaAcceptanceRequired()

    async def policy_status(
        self, *, policy: NdaPolicy | None, subject: NdaSubject
    ) -> tuple[NdaPolicy | None, bool]:
        """Return (policy, accepted). accepted is True when there is no policy."""
        if policy is None:
            return None, True
        return policy, await self._is_accepted(policy=policy, subject=subject)

    async def room_policy_status(
        self, *, tenant_id: str, room_id: str, subject: NdaSubject
    ) -> tuple[NdaPolicy | None, bool]:
        policy = await self._storage.get_nda_policy(
            tenant_id=tenant_id, scope_type="room", scope_id=room_id
        )
        return await self.policy_status(policy=policy, subject=subject)

    async def require_room_accepted(
        self, *, tenant_id: str, room_id: str, subject: NdaSubject
    ) -> None:
        _, accepted = await self.room_policy_status(
            tenant_id=tenant_id, room_id=room_id, subject=subject
        )
        if not accepted:
            raise NdaAcceptanceRequired()

    async def accept(
        self,
        *,
        policy: NdaPolicy,
        subject: NdaSubject,
        typed_name: str,
        scroll_confirmed: bool,
        checkbox_confirmed: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NdaAcceptance:
        name = (typed_name or "").strip()
        if policy.require_typed_signature and not name:
            raise NdaError("nda_signature_required")
        if policy.require_scroll and not scroll_confirmed:
            raise NdaError("nda_scroll_required")
        if not checkbox_confirmed:
            raise NdaError("nda_agreement_required")

        acceptance = NdaAcceptance(
            id=self._storage.generate_id("ndaacc"),
            tenant_id=policy.tenant_id,
            nda_policy_id=policy.id,
            scope_type=policy.scope_type,
            scope_id=policy.scope_id,
            nda_version=policy.version,
            subject_kind=subject.subject_kind,
            subject_id=subject.subject_id,
            external_party_id=subject.external_party_id,
            presented_email=subject.presented_email,
            typed_name=name,
            scroll_confirmed=bool(scroll_confirmed),
            checkbox_confirmed=bool(checkbox_confirmed),
            session_id=subject.session_id,
            ip_hash=self._hash(ip_address),
            ua_hash=self._hash(user_agent),
            accepted_at=self._now(),
        )
        await self._storage.save_nda_acceptance(acceptance)
        
        # Emit nda.accepted event for email notification
        if self._event_bus:
            await self._event_bus.publish_event(
                policy.tenant_id,
                "nda.accepted",
                {
                    "nda_policy_id": policy.id,
                    "nda_policy_title": policy.title,
                    "scope_type": policy.scope_type.value,
                    "scope_id": policy.scope_id,
                    "subject_kind": subject.subject_kind.value,
                    "subject_id": subject.subject_id,
                    "subject_email": subject.presented_email,
                    "typed_name": name,
                    "accepted_at": acceptance.accepted_at.isoformat(),
                },
            )
            if subject.external_party_id or subject.presented_email:
                await self._event_bus.publish_event(
                    policy.tenant_id,
                    "recipient.nda_accepted",
                    {
                        "tenant_id": policy.tenant_id,
                        "owner_user_id": None,
                        "document_id": (
                            policy.scope_id
                            if policy.scope_type == NdaScopeType.DOCUMENT
                            else None
                        ),
                        "room_id": (
                            policy.scope_id
                            if policy.scope_type == NdaScopeType.ROOM
                            else None
                        ),
                        "external_party_id": subject.external_party_id,
                        "visitor_session_id": subject.session_id,
                        "occurred_at": acceptance.accepted_at.isoformat(),
                    },
                )
        
        return acceptance

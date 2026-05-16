from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain import EventType, VisitorSession, ViewEvent
from app.ports.object_storage_port import ObjectStoragePort
from app.ports.storage_port import StoragePort
from app.services.document_service import DocumentService
from app.services.link_service import LinkService


@dataclass(frozen=True)
class ResolvedViewSession:
    session: VisitorSession
    link_id: str
    document_id: str
    document_name: str
    mime_type: str
    size: int
    storage_key: str
    can_download: bool
    can_print: bool
    require_email: bool
    allowed_emails: list[str]
    email: str | None
    revoked: bool = False
    expired: bool = False


@dataclass(frozen=True)
class StreamedDocument:
    content: bytes
    media_type: str
    filename: str


class ViewerService:
    def __init__(
        self,
        *,
        storage: StoragePort,
        object_storage: ObjectStoragePort,
        document_service: DocumentService,
        link_service: LinkService,
    ) -> None:
        self._storage = storage
        self._object_storage = object_storage
        self._document_service = document_service
        self._link_service = link_service

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _hash(value: str | None) -> str | None:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    async def inspect_share_token(self, *, tenant_id: str, document_id: str, link_id: str) -> dict:
        link = await self._link_service.get_share_link(tenant_id=tenant_id, link_id=link_id)
        document = await self._document_service.get_document(tenant_id=tenant_id, document_id=document_id)
        if not link or not document or link.document_id != document_id:
            raise ValueError("not_found")
        now = self._now()
        return {
            "link": link,
            "document": document,
            "revoked": bool(link.revoked_at),
            "expired": bool(link.expires_at <= now),
        }

    async def create_view_session(
        self,
        *,
        tenant_id: str,
        document_id: str,
        link_id: str,
        email: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> VisitorSession:
        inspection = await self.inspect_share_token(
            tenant_id=tenant_id,
            document_id=document_id,
            link_id=link_id,
        )
        link = inspection["link"]
        document = inspection["document"]
        if inspection["revoked"]:
            raise ValueError("revoked")
        if inspection["expired"]:
            raise ValueError("expired")
        normalized_email = email.strip().lower() if email else None
        if link.require_email and not normalized_email:
            raise ValueError("email_required")
        if link.allowed_emails:
            allowed = {item.strip().lower() for item in link.allowed_emails}
            if normalized_email not in allowed:
                raise ValueError("email_not_allowed")

        session = VisitorSession(
            id=self._storage.generate_id("vs"),
            tenant_id=tenant_id,
            share_link_id=link.id,
            visitor_id=normalized_email,
            ip_hash=self._hash(ip_address),
            ua_hash=self._hash(user_agent),
            started_at=self._now(),
            ended_at=None,
        )
        await self._storage.save_visitor_session(session)
        await self._storage.save_view_event(
            ViewEvent(
                id=self._storage.generate_id("evt"),
                tenant_id=tenant_id,
                document_id=document.id,
                share_link_id=link.id,
                visitor_session_id=session.id,
                event_type=EventType.OPEN,
                timestamp=self._now(),
            )
        )
        await self._storage.save_view_event(
            ViewEvent(
                id=self._storage.generate_id("evt"),
                tenant_id=tenant_id,
                document_id=document.id,
                share_link_id=link.id,
                visitor_session_id=session.id,
                event_type=EventType.PAGE_VIEW,
                page_number=1,
                duration_ms=0,
                timestamp=self._now(),
            )
        )
        return session

    async def resolve_view_session(self, *, session_id: str) -> ResolvedViewSession:
        session = await self._storage.get_visitor_session_by_id(session_id=session_id)
        if not session:
            raise ValueError("session_not_found")
        return await self.resolve_view_session_for_tenant(tenant_id=session.tenant_id, session_id=session_id)

    async def resolve_view_session_for_tenant(self, *, tenant_id: str, session_id: str) -> ResolvedViewSession:
        session = await self._storage.get_visitor_session(tenant_id=tenant_id, session_id=session_id)
        if not session:
            raise ValueError("session_not_found")
        link = await self._link_service.get_share_link(tenant_id=tenant_id, link_id=session.share_link_id)
        if not link:
            raise ValueError("link_not_found")
        document = await self._document_service.get_document(tenant_id=tenant_id, document_id=link.document_id)
        if not document:
            raise ValueError("document_not_found")
        now = self._now()
        return ResolvedViewSession(
            session=session,
            link_id=link.id,
            document_id=document.id,
            document_name=document.name,
            mime_type=document.mime_type,
            size=document.size,
            storage_key=document.storage_key,
            can_download=link.can_download,
            can_print=link.can_print,
            require_email=link.require_email,
            allowed_emails=list(link.allowed_emails or []),
            email=session.visitor_id,
            revoked=bool(link.revoked_at),
            expired=bool(link.expires_at <= now),
        )

    async def resolve_view_session_any_tenant(self, *, session_id: str) -> ResolvedViewSession:
        return await self.resolve_view_session(session_id=session_id)

    async def ensure_active_session(self, *, tenant_id: str, session_id: str) -> ResolvedViewSession:
        resolved = await self.resolve_view_session_for_tenant(tenant_id=tenant_id, session_id=session_id)
        if resolved.session.ended_at is not None:
            raise ValueError("session_closed")
        if resolved.revoked:
            raise ValueError("revoked")
        if resolved.expired:
            raise ValueError("expired")
        return resolved

    async def record_heartbeat(
        self,
        *,
        tenant_id: str,
        session_id: str,
        page_number: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        resolved = await self.ensure_active_session(tenant_id=tenant_id, session_id=session_id)
        await self._storage.save_view_event(
            ViewEvent(
                id=self._storage.generate_id("evt"),
                tenant_id=tenant_id,
                document_id=resolved.document_id,
                share_link_id=resolved.link_id,
                visitor_session_id=session_id,
                event_type=EventType.HEARTBEAT,
                page_number=page_number,
                duration_ms=duration_ms,
                timestamp=self._now(),
            )
        )

    async def close_session(self, *, tenant_id: str, session_id: str) -> None:
        resolved = await self.resolve_view_session_for_tenant(tenant_id=tenant_id, session_id=session_id)
        if resolved.session.ended_at is None:
            ended_at = self._now()
            await self._storage.end_visitor_session(tenant_id=tenant_id, session_id=session_id, ended_at=ended_at)
            await self._storage.save_view_event(
                ViewEvent(
                    id=self._storage.generate_id("evt"),
                    tenant_id=tenant_id,
                    document_id=resolved.document_id,
                    share_link_id=resolved.link_id,
                    visitor_session_id=session_id,
                    event_type=EventType.CLOSE,
                    timestamp=ended_at,
                )
            )

    async def record_download_attempt(self, *, tenant_id: str, session_id: str, blocked: bool = False) -> None:
        resolved = await self.resolve_view_session_for_tenant(tenant_id=tenant_id, session_id=session_id)
        await self._storage.save_view_event(
            ViewEvent(
                id=self._storage.generate_id("evt"),
                tenant_id=tenant_id,
                document_id=resolved.document_id,
                share_link_id=resolved.link_id,
                visitor_session_id=session_id,
                event_type=EventType.BLOCKED if blocked else EventType.DOWNLOAD_ATTEMPT,
                timestamp=self._now(),
            )
        )

    async def _read_streamed_document(self, *, resolved: ResolvedViewSession) -> StreamedDocument:
        content = await self._object_storage.read_object(object_key=resolved.storage_key)
        return StreamedDocument(
            content=content,
            media_type=resolved.mime_type or "application/octet-stream",
            filename=resolved.document_name,
        )

    async def stream_document(self, *, session_id: str) -> StreamedDocument:
        resolved = await self.resolve_view_session(session_id=session_id)
        active = await self.ensure_active_session(
            tenant_id=resolved.session.tenant_id,
            session_id=session_id,
        )
        return await self._read_streamed_document(resolved=active)

    async def download_document(self, *, tenant_id: str, session_id: str) -> StreamedDocument:
        resolved = await self.ensure_active_session(tenant_id=tenant_id, session_id=session_id)
        return await self._read_streamed_document(resolved=resolved)

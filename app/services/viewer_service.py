from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain import EventType, VisitorSession, ViewEvent
from app.ports.object_storage_port import ObjectStoragePort
from app.ports.rendered_page_cache_port import RenderedPageCachePort
from app.ports.storage_port import StoragePort
from app.ports.task_queue_port import TaskQueuePort
from app.services.document_processor import (
    DocumentProcessor,
    DocumentProcessingError,
    PdfPreview,
    ProcessedDocument,
    ProcessingContext,
    RenderedPage,
    ViewPolicy,
)
from app.services.document_service import DocumentService
from app.services.link_service import LinkService
from app.services.nda_service import NdaService


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
class ViewSessionDelivery:
    resolved: ResolvedViewSession
    view_policy: ViewPolicy
    pdf_preview: PdfPreview | None = None


class _BytesCache:
    def __init__(self, *, maxsize: int = 50, ttl_seconds: float = 300.0) -> None:
        self._cache: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> bytes | None:
        async with self._lock:
            now = time.monotonic()
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if now >= expires_at:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: bytes) -> None:
        async with self._lock:
            self._cache[key] = (value, time.monotonic() + self._ttl_seconds)
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)


class ViewerService:
    def __init__(
        self,
        *,
        storage: StoragePort,
        object_storage: ObjectStoragePort,
        rendered_page_cache: RenderedPageCachePort,
        task_queue: TaskQueuePort,
        document_processor: DocumentProcessor,
        document_service: DocumentService,
        link_service: LinkService,
        nda_service: NdaService | None = None,
    ) -> None:
        self._storage = storage
        self._object_storage = object_storage
        self._rendered_page_cache = rendered_page_cache
        self._task_queue = task_queue
        self._document_processor = document_processor
        self._document_service = document_service
        self._link_service = link_service
        self._nda_service = nda_service
        self._content_cache = _BytesCache(maxsize=50, ttl_seconds=300.0)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _hash(value: str | None) -> str | None:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_watermark_text(*, resolved: ResolvedViewSession) -> str:
        identifier = resolved.email or resolved.link_id
        return f"HexShare - {identifier}"

    def _build_processing_context(
        self,
        *,
        resolved: ResolvedViewSession,
        session_id: str,
        download: bool,
    ) -> ProcessingContext:
        return ProcessingContext(
            document_id=resolved.document_id,
            session_id=session_id,
            filename=resolved.document_name,
            source_media_type=resolved.mime_type or "application/octet-stream",
            watermark_text=self._build_watermark_text(resolved=resolved),
            download=download,
        )

    @staticmethod
    def _duration_ms(*, started_at: datetime, ended_at: datetime) -> int:
        delta = ended_at - started_at
        return max(int(delta.total_seconds() * 1000), 0)

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
        external_party_id: str | None = None
        external_access_grant_id: str | None = link.external_access_grant_id
        identity_source: str | None = "manual_entry" if normalized_email else None
        if link.allowed_emails:
            allowed = {item.strip().lower() for item in link.allowed_emails}
            if normalized_email not in allowed:
                raise ValueError("email_not_allowed")
        if link.bound_email_normalized:
            if normalized_email != link.bound_email_normalized:
                raise ValueError("email_not_allowed")
            identity_source = "bound_party_email"
        if link.external_access_grant_id:
            grant = await self._storage.get_external_access_grant(
                tenant_id=tenant_id,
                grant_id=link.external_access_grant_id,
            )
            if grant is None or grant.revoked_at is not None:
                raise ValueError("revoked")
            if grant.expires_at is not None and grant.expires_at <= self._now():
                raise ValueError("expired")
            external_access_grant_id = grant.id
            external_party_id = grant.external_party_id
            party = await self._storage.get_external_party(
                tenant_id=tenant_id,
                external_party_id=grant.external_party_id,
            )
            if party is None:
                raise ValueError("not_found")
            if party.status.value in {"blocked", "revoked", "archived"}:
                raise ValueError("revoked")
            if normalized_email:
                await self._storage.mark_external_party_email_seen(
                    tenant_id=tenant_id,
                    email_normalized=normalized_email,
                    seen_at=self._now(),
                    verified_at=self._now(),
                )

        session = VisitorSession(
            id=self._storage.generate_id("vs"),
            tenant_id=tenant_id,
            share_link_id=link.id,
            visitor_id=normalized_email,
            external_party_id=external_party_id,
            external_access_grant_id=external_access_grant_id,
            presented_email=normalized_email,
            identity_source=identity_source,
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

    async def describe_view_session_delivery(self, *, tenant_id: str, session_id: str) -> ViewSessionDelivery:
        resolved = await self.ensure_active_session(tenant_id=tenant_id, session_id=session_id)
        view_policy = self._document_processor.describe_view_policy(
            filename=resolved.document_name,
            source_media_type=resolved.mime_type,
        )
        pdf_preview: PdfPreview | None = None
        if view_policy.inline_view_supported and view_policy.view_kind == "pdf":
            content = await self._read_object_cached(object_key=resolved.storage_key)
            pdf_preview = await self._document_processor.describe_pdf_preview(
                content=content,
                cache_key=resolved.storage_key,
            )

        return ViewSessionDelivery(
            resolved=resolved,
            view_policy=view_policy,
            pdf_preview=pdf_preview,
        )

    async def ensure_active_session(self, *, tenant_id: str, session_id: str) -> ResolvedViewSession:
        resolved = await self.resolve_view_session_for_tenant(tenant_id=tenant_id, session_id=session_id)
        if resolved.session.ended_at is not None:
            raise ValueError("session_closed")
        if resolved.revoked:
            raise ValueError("revoked")
        if resolved.expired:
            raise ValueError("expired")
        return resolved

    async def nda_status(self, *, session_id: str):
        """Applicable + outstanding NDA policies for a share-link session's document.

        Does not enforce (so the frontend can render the gate). Returns
        ``(resolved, applicable, outstanding)``; applicable/outstanding are empty
        when NDA is disabled.
        """
        resolved = await self.resolve_view_session(session_id=session_id)
        if self._nda_service is None:
            return resolved, [], []
        document = await self._document_service.get_document(
            tenant_id=resolved.session.tenant_id, document_id=resolved.document_id
        )
        if document is None:
            return resolved, [], []
        subject = NdaService.subject_from_view_session(resolved)
        applicable = await self._nda_service.applicable_policies(document=document)
        outstanding = await self._nda_service.outstanding_policies(document=document, subject=subject)
        return resolved, applicable, outstanding

    async def _enforce_nda(self, *, resolved: ResolvedViewSession) -> None:
        if self._nda_service is None:
            return
        document = await self._document_service.get_document(
            tenant_id=resolved.session.tenant_id, document_id=resolved.document_id
        )
        if document is None:
            return
        subject = NdaService.subject_from_view_session(resolved)
        await self._nda_service.require_all_accepted(document=document, subject=subject)

    async def record_page_view(
        self,
        *,
        tenant_id: str,
        session_id: str,
        page_number: int,
    ) -> None:
        resolved = await self.ensure_active_session(tenant_id=tenant_id, session_id=session_id)
        now = self._now()
        previous_page_view = await self._storage.get_latest_page_view_event(
            tenant_id=tenant_id,
            visitor_session_id=session_id,
        )
        if previous_page_view and previous_page_view.duration_ms is None:
            await self._storage.update_view_event_duration(
                tenant_id=tenant_id,
                event_id=previous_page_view.id,
                duration_ms=self._duration_ms(
                    started_at=previous_page_view.timestamp,
                    ended_at=now,
                ),
            )
        await self._storage.save_view_event(
            ViewEvent(
                id=self._storage.generate_id("evt"),
                tenant_id=tenant_id,
                document_id=resolved.document_id,
                share_link_id=resolved.link_id,
                visitor_session_id=session_id,
                event_type=EventType.PAGE_VIEW,
                page_number=page_number,
                duration_ms=None,
                timestamp=now,
            )
        )
        # Fire-and-forget hook for async pre-render worker pipelines.
        try:
            await self._task_queue.enqueue_prerender_page(
                session_id=session_id,
                page_number=page_number + 1,
                render_width=None,
            )
        except Exception:
            # Queue transport failures must not block the user path.
            pass

    async def close_session(self, *, tenant_id: str, session_id: str) -> None:
        resolved = await self.resolve_view_session_for_tenant(tenant_id=tenant_id, session_id=session_id)
        if resolved.session.ended_at is None:
            ended_at = self._now()
            previous_page_view = await self._storage.get_latest_page_view_event(
                tenant_id=tenant_id,
                visitor_session_id=session_id,
            )
            if previous_page_view and previous_page_view.duration_ms is None:
                await self._storage.update_view_event_duration(
                    tenant_id=tenant_id,
                    event_id=previous_page_view.id,
                    duration_ms=self._duration_ms(
                        started_at=previous_page_view.timestamp,
                        ended_at=ended_at,
                    ),
                )
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

    async def _process_document(
        self,
        *,
        resolved: ResolvedViewSession,
        session_id: str,
        download: bool,
    ) -> ProcessedDocument:
        content = await self._read_object_cached(object_key=resolved.storage_key)
        context = self._build_processing_context(
            resolved=resolved,
            session_id=session_id,
            download=download,
        )
        if download:
            return await self._document_processor.process_for_download(
                context=context,
                content=content,
            )
        return await self._document_processor.process_for_view(
            context=context,
            content=content,
        )

    async def stream_document(self, *, session_id: str) -> ProcessedDocument:
        resolved = await self.resolve_view_session(session_id=session_id)
        active = await self.ensure_active_session(
            tenant_id=resolved.session.tenant_id,
            session_id=session_id,
        )
        view_policy = self._document_processor.describe_view_policy(
            filename=active.document_name,
            source_media_type=active.mime_type,
        )
        if view_policy.view_kind == "pdf":
            raise DocumentProcessingError("page_image_view_required")
        await self._enforce_nda(resolved=active)
        return await self._process_document(
            resolved=active,
            session_id=session_id,
            download=False,
        )

    async def render_document_page(
        self,
        *,
        session_id: str,
        page_number: int,
        render_width: int | None = None,
    ) -> RenderedPage:
        resolved = await self.resolve_view_session(session_id=session_id)
        active = await self.ensure_active_session(
            tenant_id=resolved.session.tenant_id,
            session_id=session_id,
        )
        view_policy = self._document_processor.describe_view_policy(
            filename=active.document_name,
            source_media_type=active.mime_type,
        )
        if view_policy.view_kind != "pdf":
            raise DocumentProcessingError("page_image_view_not_supported")

        await self._enforce_nda(resolved=active)
        cache_key = self._build_rendered_page_cache_key(
            resolved=active,
            page_number=page_number,
            render_width=render_width,
        )
        cached_page = await self._rendered_page_cache.get(cache_key)
        if cached_page is not None:
            return cached_page

        content = await self._read_object_cached(object_key=active.storage_key)
        rendered = await self._document_processor.render_pdf_page(
            context=self._build_processing_context(
                resolved=active,
                session_id=session_id,
                download=False,
            ),
            content=content,
            page_number=page_number,
            render_width=render_width,
            cache_key=active.storage_key,
        )
        await self._rendered_page_cache.set(cache_key, rendered)
        return rendered

    async def download_document(self, *, tenant_id: str, session_id: str) -> ProcessedDocument:
        resolved = await self.ensure_active_session(tenant_id=tenant_id, session_id=session_id)
        await self._enforce_nda(resolved=resolved)
        return await self._process_document(
            resolved=resolved,
            session_id=session_id,
            download=True,
        )

    async def _read_object_cached(self, *, object_key: str) -> bytes:
        cached = await self._content_cache.get(object_key)
        if cached is not None:
            return cached
        content = await self._object_storage.read_object(object_key=object_key)
        await self._content_cache.set(object_key, content)
        return content

    def _build_rendered_page_cache_key(
        self,
        *,
        resolved: ResolvedViewSession,
        page_number: int,
        render_width: int | None,
    ) -> str:
        watermark_text = self._build_watermark_text(resolved=resolved)
        watermark_hash = hashlib.sha256(watermark_text.encode("utf-8")).hexdigest()
        width_value = render_width if render_width is not None else 1400
        return f"{resolved.storage_key}|{page_number}|{width_value}|{watermark_hash}"

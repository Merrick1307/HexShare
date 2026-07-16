from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone

from app.ports.access_control import AccessDenied
from app.domain import Document, ExternalRoomEvent, ExternalRoomEventType
from app.ports.object_storage_port import ObjectStoragePort
from app.ports.rendered_page_cache_port import RenderedPageCachePort
from app.ports.storage_port import StoragePort
from app.core.authz import ResourceAction
from app.services.document_processor import (
    DocumentProcessingError,
    DocumentProcessor,
    PdfPreview,
    ProcessedDocument,
    ProcessingContext,
    RenderedPage,
    ViewPolicy,
)
from app.services.document_service import DocumentService
from app.services.external_room_access_service import ExternalRoomPrincipal
from app.services.nda_service import NdaService


@dataclass(frozen=True)
class ResolvedExternalRoomDocumentSession:
    session_id: str
    room_session_id: str
    principal: ExternalRoomPrincipal
    document_id: str
    document_name: str
    mime_type: str
    size: int
    storage_key: str
    can_download: bool
    can_print: bool


@dataclass(frozen=True)
class ExternalRoomDocumentSessionDelivery:
    resolved: ResolvedExternalRoomDocumentSession
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
            now = asyncio.get_running_loop().time()
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
            self._cache[key] = (value, asyncio.get_running_loop().time() + self._ttl_seconds)
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)


class ExternalRoomViewerService:
    def __init__(
        self,
        *,
        storage: StoragePort,
        object_storage: ObjectStoragePort,
        rendered_page_cache: RenderedPageCachePort,
        document_processor: DocumentProcessor,
        document_service: DocumentService,
        nda_service: NdaService | None = None,
    ) -> None:
        self._storage = storage
        self._object_storage = object_storage
        self._rendered_page_cache = rendered_page_cache
        self._document_processor = document_processor
        self._document_service = document_service
        self._nda_service = nda_service
        self._content_cache = _BytesCache(maxsize=50, ttl_seconds=300.0)

    async def _enforce_nda(self, *, principal: ExternalRoomPrincipal, document: Document) -> None:
        if self._nda_service is None:
            return
        subject = NdaService.subject_from_room_principal(principal)
        await self._nda_service.require_all_accepted(document=document, subject=subject)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _build_session_id(*, room_session_id: str, document_id: str) -> str:
        return f"{room_session_id}.{document_id}"

    @staticmethod
    def _parse_session_id(session_id: str) -> tuple[str, str]:
        room_session_id, separator, document_id = session_id.partition(".")
        if not separator or not room_session_id or not document_id:
            raise ValueError("session_not_found")
        return room_session_id, document_id

    @staticmethod
    def _build_watermark_text(*, principal: ExternalRoomPrincipal) -> str:
        identifier = principal.email
        if principal.display_name:
            identifier = f"{principal.display_name} <{principal.email}>"
        return f"HexShare - {identifier}"

    def _build_processing_context(
        self,
        *,
        resolved: ResolvedExternalRoomDocumentSession,
        download: bool,
    ) -> ProcessingContext:
        return ProcessingContext(
            document_id=resolved.document_id,
            session_id=resolved.session_id,
            filename=resolved.document_name,
            source_media_type=resolved.mime_type or "application/octet-stream",
            watermark_text=self._build_watermark_text(principal=resolved.principal),
            download=download,
        )

    @staticmethod
    def _duration_ms(*, started_at: datetime, ended_at: datetime) -> int:
        delta = ended_at - started_at
        return max(int(delta.total_seconds() * 1000), 0)

    async def _read_object_cached(self, *, object_key: str) -> bytes:
        cached = await self._content_cache.get(object_key)
        if cached is not None:
            return cached
        content = await self._object_storage.read_object(object_key=object_key)
        await self._content_cache.set(object_key, content)
        return content

    async def _require_document(
        self,
        *,
        principal: ExternalRoomPrincipal,
        document_id: str,
        required_permission: int,
    ) -> Document:
        document = await self._document_service.require_document_access(
            principal=principal.as_tenant_principal(),
            document_id=document_id,
            required=required_permission,
        )
        if document.room_id != principal.room_id:
            raise AccessDenied("Document is not part of this external room")
        await self._enforce_nda(principal=principal, document=document)
        return document

    async def _resolve_session(
        self,
        *,
        principal: ExternalRoomPrincipal,
        session_id: str,
        required_permission: int,
    ) -> ResolvedExternalRoomDocumentSession:
        room_session_id, document_id = self._parse_session_id(session_id)
        if room_session_id != principal.session_id:
            raise ValueError("session_not_found")
        document = await self._require_document(
            principal=principal,
            document_id=document_id,
            required_permission=required_permission,
        )
        return ResolvedExternalRoomDocumentSession(
            session_id=session_id,
            room_session_id=room_session_id,
            principal=principal,
            document_id=document.id,
            document_name=document.name,
            mime_type=document.mime_type,
            size=document.size,
            storage_key=document.storage_key,
            can_download=principal.can_download,
            can_print=principal.can_print,
        )

    async def create_view_session(
        self,
        *,
        principal: ExternalRoomPrincipal,
        document_id: str,
    ) -> ExternalRoomDocumentSessionDelivery:
        document = await self._require_document(
            principal=principal,
            document_id=document_id,
            required_permission=int(ResourceAction.READ),
        )
        session_id = self._build_session_id(room_session_id=principal.session_id, document_id=document.id)
        resolved = ResolvedExternalRoomDocumentSession(
            session_id=session_id,
            room_session_id=principal.session_id,
            principal=principal,
            document_id=document.id,
            document_name=document.name,
            mime_type=document.mime_type,
            size=document.size,
            storage_key=document.storage_key,
            can_download=principal.can_download,
            can_print=principal.can_print,
        )
        await self._storage.save_external_room_event(
            ExternalRoomEvent(
                id=self._storage.generate_id("ere"),
                tenant_id=principal.tenant_id,
                external_room_session_id=principal.session_id,
                room_id=principal.room_id,
                event_type=ExternalRoomEventType.DOCUMENT_VIEW_OPEN,
                document_id=document.id,
                timestamp=self._now(),
            )
        )
        return await self._describe_delivery(resolved=resolved)

    async def describe_view_session(
        self,
        *,
        principal: ExternalRoomPrincipal,
        session_id: str,
    ) -> ExternalRoomDocumentSessionDelivery:
        resolved = await self._resolve_session(
            principal=principal,
            session_id=session_id,
            required_permission=int(ResourceAction.READ),
        )
        return await self._describe_delivery(resolved=resolved)

    async def _describe_delivery(
        self,
        *,
        resolved: ResolvedExternalRoomDocumentSession,
    ) -> ExternalRoomDocumentSessionDelivery:
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
        return ExternalRoomDocumentSessionDelivery(
            resolved=resolved,
            view_policy=view_policy,
            pdf_preview=pdf_preview,
        )

    async def stream_document(
        self,
        *,
        principal: ExternalRoomPrincipal,
        session_id: str,
    ) -> ProcessedDocument:
        resolved = await self._resolve_session(
            principal=principal,
            session_id=session_id,
            required_permission=int(ResourceAction.READ),
        )
        view_policy = self._document_processor.describe_view_policy(
            filename=resolved.document_name,
            source_media_type=resolved.mime_type,
        )
        if view_policy.view_kind == "pdf":
            raise DocumentProcessingError("page_image_view_required")
        content = await self._read_object_cached(object_key=resolved.storage_key)
        return await self._document_processor.process_for_view(
            context=self._build_processing_context(resolved=resolved, download=False),
            content=content,
        )

    async def render_document_page(
        self,
        *,
        principal: ExternalRoomPrincipal,
        session_id: str,
        page_number: int,
        render_width: int | None = None,
    ) -> RenderedPage:
        resolved = await self._resolve_session(
            principal=principal,
            session_id=session_id,
            required_permission=int(ResourceAction.READ),
        )
        view_policy = self._document_processor.describe_view_policy(
            filename=resolved.document_name,
            source_media_type=resolved.mime_type,
        )
        if view_policy.view_kind != "pdf":
            raise DocumentProcessingError("page_image_view_not_supported")

        cache_key = self._build_rendered_page_cache_key(
            resolved=resolved,
            page_number=page_number,
            render_width=render_width,
        )
        cached_page = await self._rendered_page_cache.get(cache_key)
        if cached_page is not None:
            return cached_page

        content = await self._read_object_cached(object_key=resolved.storage_key)
        rendered = await self._document_processor.render_pdf_page(
            context=self._build_processing_context(resolved=resolved, download=False),
            content=content,
            page_number=page_number,
            render_width=render_width,
            cache_key=resolved.storage_key,
        )
        await self._rendered_page_cache.set(cache_key, rendered)
        return rendered

    async def download_document(
        self,
        *,
        principal: ExternalRoomPrincipal,
        session_id: str,
    ) -> ProcessedDocument:
        if not principal.can_download:
            raise ValueError("download_not_allowed")
        resolved = await self._resolve_session(
            principal=principal,
            session_id=session_id,
            required_permission=int(ResourceAction.EXPORT),
        )
        content = await self._read_object_cached(object_key=resolved.storage_key)
        return await self._document_processor.process_for_download(
            context=self._build_processing_context(resolved=resolved, download=True),
            content=content,
        )

    async def close_view_session(
        self,
        *,
        principal: ExternalRoomPrincipal,
        session_id: str,
    ) -> None:
        resolved = await self._resolve_session(
            principal=principal,
            session_id=session_id,
            required_permission=int(ResourceAction.READ),
        )
        now = self._now()
        previous_page_view = await self._storage.get_latest_external_room_page_view_event(
            tenant_id=principal.tenant_id,
            external_room_session_id=principal.session_id,
            document_id=resolved.document_id,
        )
        if previous_page_view and previous_page_view.duration_ms is None:
            await self._storage.update_external_room_event_duration(
                tenant_id=principal.tenant_id,
                event_id=previous_page_view.id,
                duration_ms=self._duration_ms(
                    started_at=previous_page_view.timestamp,
                    ended_at=now,
                ),
            )
        await self._storage.save_external_room_event(
            ExternalRoomEvent(
                id=self._storage.generate_id("ere"),
                tenant_id=principal.tenant_id,
                external_room_session_id=principal.session_id,
                room_id=principal.room_id,
                event_type=ExternalRoomEventType.DOCUMENT_VIEW_CLOSE,
                document_id=resolved.document_id,
                timestamp=now,
            )
        )

    async def record_page_view(
        self,
        *,
        principal: ExternalRoomPrincipal,
        session_id: str,
        page_number: int,
    ) -> None:
        resolved = await self._resolve_session(
            principal=principal,
            session_id=session_id,
            required_permission=int(ResourceAction.READ),
        )
        now = self._now()
        previous_page_view = await self._storage.get_latest_external_room_page_view_event(
            tenant_id=principal.tenant_id,
            external_room_session_id=principal.session_id,
            document_id=resolved.document_id,
        )
        if previous_page_view and previous_page_view.duration_ms is None:
            await self._storage.update_external_room_event_duration(
                tenant_id=principal.tenant_id,
                event_id=previous_page_view.id,
                duration_ms=self._duration_ms(
                    started_at=previous_page_view.timestamp,
                    ended_at=now,
                ),
            )
        await self._storage.save_external_room_event(
            ExternalRoomEvent(
                id=self._storage.generate_id("ere"),
                tenant_id=principal.tenant_id,
                external_room_session_id=principal.session_id,
                room_id=principal.room_id,
                event_type=ExternalRoomEventType.DOCUMENT_PAGE_VIEW,
                document_id=resolved.document_id,
                page_number=page_number,
                duration_ms=None,
                timestamp=now,
            )
        )

    def _build_rendered_page_cache_key(
        self,
        *,
        resolved: ResolvedExternalRoomDocumentSession,
        page_number: int,
        render_width: int | None,
    ) -> str:
        width_value = render_width if render_width is not None else 1400
        return f"{resolved.storage_key}|{page_number}|{width_value}|{resolved.principal.external_party_id}"

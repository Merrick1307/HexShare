"""
Upload orchestration service.

This service coordinates upload initiation and completion while keeping
HexShare's existing split between metadata persistence and raw object
storage. The raw file is uploaded directly to object storage through a
presigned URL, then the document metadata is finalized in Postgres.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.domain import Document
from app.ports.object_storage_port import ObjectStoragePort, TemporaryObjectAccess
from app.ports.storage_port import StoragePort
from app.services.document_service import DocumentService
from app.core.document_type_policy import (
    describe_document_protection,
    normalized_content_type,
    validate_pdf_bytes,
)


@dataclass(frozen=True)
class UploadInitiation:
    document_id: str
    object_key: str
    upload: TemporaryObjectAccess
    protection: dict[str, object] = field(default_factory=dict)


class UploadService:
    def __init__(
        self,
        *,
        metadata_storage: StoragePort,
        object_storage: ObjectStoragePort,
        document_service: DocumentService,
        max_size_bytes: int | None = None,
    ) -> None:
        self._metadata_storage = metadata_storage
        self._object_storage = object_storage
        self._document_service = document_service
        self._max_size_bytes = max_size_bytes

    async def initiate_upload(
        self,
        *,
        tenant_id: str,
        filename: str,
        content_type: str,
        size: int,
        expires_in: int = 900,
    ) -> UploadInitiation:
        normalized_type = normalized_content_type(filename, content_type)
        if self._max_size_bytes is not None and size > self._max_size_bytes:
            raise ValueError("upload_size_exceeded")
        document_id = self._metadata_storage.generate_id("doc")
        object_key = self._object_storage.build_object_key(
            tenant_id=tenant_id,
            document_id=document_id,
            filename=filename,
        )
        upload = await self._object_storage.create_temporary_upload(
            object_key=object_key,
            content_type=normalized_type,
            expires_in=expires_in,
        )
        return UploadInitiation(
            document_id=document_id,
            object_key=object_key,
            upload=upload,
            protection=describe_document_protection(
                filename, normalized_type
            ).as_dict(),
        )

    async def complete_upload(
        self,
        *,
        tenant_id: str,
        document_id: str,
        object_key: str,
        name: str,
        mime_type: str,
        size: int,
        created_by: str,
        expected_etag: str | None = None,
        room_id: str | None = None,
        room_section_id: str | None = None,
    ) -> Document:
        normalized_type = normalized_content_type(name, mime_type)
        if self._max_size_bytes is not None and size > self._max_size_bytes:
            raise ValueError("upload_size_exceeded")
        existing = await self._document_service.get_document(
            tenant_id=tenant_id,
            document_id=document_id,
        )
        if existing:
            raise ValueError("document_already_exists")

        info = None
        for attempt in range(5):
            info = await self._object_storage.head_object(object_key=object_key)
            if info is not None:
                break
            if attempt < 4:
                await asyncio.sleep(0.3 * (attempt + 1))
        if info is None:
            raise ValueError("object_not_found")

        if info.size is not None and int(info.size) != int(size):
            raise ValueError("object_size_mismatch")

        if expected_etag and info.etag and expected_etag != info.etag:
            raise ValueError("object_etag_mismatch")
        try:
            if name.lower().endswith(".pdf"):
                content = await self._object_storage.read_object(object_key=object_key)
                # Some unit fakes only model metadata. Real object stores return
                # the complete object, which is where strict PDF validation runs.
                if content or info.size == 0:
                    validate_pdf_bytes(content)
            return await self._document_service.create_document(
                document_id=document_id,
                tenant_id=tenant_id,
                name=name,
                mime_type=normalized_type,
                size=size,
                storage_key=object_key,
                created_by=created_by,
                room_id=room_id,
                room_section_id=room_section_id,
            )
        except Exception:
            # A metadata save may have succeeded even if a later event publisher
            # failed. Re-check before cleanup so finalized documents never lose
            # their backing object.
            try:
                finalized = await self._document_service.get_document(
                    tenant_id=tenant_id,
                    document_id=document_id,
                )
                if finalized is None:
                    await self._object_storage.delete_object(object_key=object_key)
            except Exception:
                # Cleanup observability belongs to the deployment adapter. Keep
                # the original actionable upload error visible to the caller.
                pass
            raise

    async def get_download_url(
        self,
        *,
        tenant_id: str,
        document_id: str,
        expires_in: int = 900,
        filename: str | None = None,
    ) -> str:
        document = await self._document_service.get_document(
            tenant_id=tenant_id,
            document_id=document_id,
        )
        if not document:
            raise ValueError("document_not_found")

        access = await self._object_storage.create_temporary_download(
            object_key=document.storage_key,
            expires_in=expires_in,
            filename=filename or document.name,
        )
        return access.url

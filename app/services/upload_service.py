"""
Upload orchestration service.

This service coordinates upload initiation and completion while keeping
HexShare's existing split between metadata persistence and raw object
storage. The raw file is uploaded directly to object storage through a
presigned URL, then the document metadata is finalized in Postgres.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.domain import Document
from app.ports.object_storage_port import ObjectStoragePort, PresignedUpload
from app.ports.storage_port import StoragePort
from app.services.document_service import DocumentService


@dataclass(frozen=True)
class UploadInitiation:
    document_id: str
    object_key: str
    upload: PresignedUpload


class UploadService:
    def __init__(
        self,
        *,
        metadata_storage: StoragePort,
        object_storage: ObjectStoragePort,
        document_service: DocumentService,
    ) -> None:
        self._metadata_storage = metadata_storage
        self._object_storage = object_storage
        self._document_service = document_service

    async def initiate_upload(
        self,
        *,
        tenant_id: str,
        filename: str,
        content_type: str,
        size: int,
        expires_in: int = 900,
    ) -> UploadInitiation:
        document_id = self._metadata_storage.generate_id("doc")
        object_key = self._object_storage.build_object_key(
            tenant_id=tenant_id,
            document_id=document_id,
            filename=filename,
        )
        upload = await self._object_storage.create_presigned_upload(
            object_key=object_key,
            content_type=content_type,
            expires_in=expires_in,
        )
        return UploadInitiation(
            document_id=document_id,
            object_key=object_key,
            upload=upload,
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
    ) -> Document:
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

        return await self._document_service.create_document(
            document_id=document_id,
            tenant_id=tenant_id,
            name=name,
            mime_type=mime_type,
            size=size,
            storage_key=object_key,
            created_by=created_by,
        )

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

        return await self._object_storage.create_presigned_download(
            object_key=document.storage_key,
            expires_in=expires_in,
            filename=filename or document.name,
        )

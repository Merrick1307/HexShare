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
from typing import Iterable

from app.domain import Document
from app.ports.storage_port import StoragePort
from app.ports import EventBusPort


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
    ) -> Document:
        """Create a new document record.

        This method assumes that the raw file has already been uploaded
        to the storage backend and that a `storage_key` referencing
        the object is available.  It persists a :class:`Document` and
        returns it.

        Parameters
        ----------
        tenant_id:
            Workspace identifier.
        name:
            The file name provided by the uploader.
        mime_type:
            MIME type of the uploaded file.
        size:
            Size of the file in bytes.
        storage_key:
            Key or path to the file in the object store.
        created_by:
            Identifier of the user who uploaded the document.

        Returns
        -------
        Document
            The newly created document metadata record.
        """
        doc_id = self._storage.generate_id("doc")
        document = Document(
            id=doc_id,
            tenant_id=tenant_id,
            name=name,
            mime_type=mime_type,
            size=size,
            storage_key=storage_key,
            created_at=datetime.utcnow(),
            created_by=created_by,
        )
        await self._storage.save_document(document)
        await self._event_bus.publish_event(
            tenant_id,
            "document.created",
            {
                "document_id": doc_id,
                "name": name,
                "mime_type": mime_type,
                "size": size,
                "created_by": created_by,
            },
        )
        return document

    async def get_document(self, *, tenant_id: str, document_id: str) -> Document | None:
        """Retrieve a document by ID.

        Returns ``None`` if the document does not exist or belongs to a
        different tenant.
        """
        return await self._storage.get_document(tenant_id=tenant_id, document_id=document_id)

    async def list_documents(self, *, tenant_id: str) -> Iterable[Document]:
        """List all documents belonging to a tenant."""
        return await self._storage.list_documents(tenant_id=tenant_id)

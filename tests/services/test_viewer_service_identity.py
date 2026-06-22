from __future__ import annotations

import pytest

from app.adapters import MemoryStorage, NoopEventBus
from app.ports.token_port import TokenPort
from app.services.document_service import DocumentService
from app.services.link_service import LinkService
from app.services.viewer_service import ViewerService


class _FakeTokenPort(TokenPort):
    def __init__(self) -> None:
        self._counter = 0

    def generate_jti(self) -> str:
        self._counter += 1
        return f"jti_{self._counter}"

    def encode_share_token(
        self, *, tenant_id, document_id, link_id, jti, expires_at, permissions, require_email
    ) -> str:
        return f"token:{tenant_id}:{document_id}:{link_id}:{jti}"

    def decode_share_token(self, token: str) -> dict:
        parts = token.split(":")
        return {"tenant_id": parts[1], "document_id": parts[2], "link_id": parts[3], "jti": parts[4]}

    async def revoke_jti(self, jti: str, expires_at) -> None:
        return None


class _UnusedObject:
    pass


async def _make_viewer_service():
    storage = MemoryStorage()
    event_bus = NoopEventBus()
    token_port = _FakeTokenPort()
    document_service = DocumentService(storage=storage, event_bus=event_bus)
    link_service = LinkService(storage=storage, token_port=token_port, event_bus=event_bus)
    viewer_service = ViewerService(
        storage=storage,
        object_storage=_UnusedObject(),  # type: ignore[arg-type]
        rendered_page_cache=_UnusedObject(),  # type: ignore[arg-type]
        task_queue=_UnusedObject(),  # type: ignore[arg-type]
        document_processor=_UnusedObject(),  # type: ignore[arg-type]
        document_service=document_service,
        link_service=link_service,
    )
    return storage, document_service, link_service, viewer_service


@pytest.mark.asyncio
async def test_create_view_session_binds_to_external_party_identity():
    storage, document_service, link_service, viewer_service = await _make_viewer_service()

    document = await document_service.create_document(
        tenant_id="tenant-1",
        name="report.pdf",
        mime_type="application/pdf",
        size=128,
        storage_key="docs/report.pdf",
        created_by="user-1",
    )
    link = await link_service.create_share_link(
        tenant_id="tenant-1",
        document_id=document.id,
        created_by="user-1",
        expires_in_seconds=3600,
        recipient_email="viewer@example.com",
        recipient_display_name="Viewer",
    )

    session = await viewer_service.create_view_session(
        tenant_id="tenant-1",
        document_id=document.id,
        link_id=link.id,
        email="viewer@example.com",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )

    assert session.external_party_id is not None
    assert session.external_access_grant_id == link.external_access_grant_id
    assert session.presented_email == "viewer@example.com"
    assert session.identity_source == "bound_party_email"

    persisted = await storage.get_visitor_session(tenant_id="tenant-1", session_id=session.id)
    assert persisted is not None
    assert persisted.external_party_id == session.external_party_id
    assert persisted.external_access_grant_id == session.external_access_grant_id

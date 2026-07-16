from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WorkspaceSummaryResponse(BaseModel):
    documents: int = 0
    groups: int = 0
    active_links: int = 0
    external_recipients: int = 0
    document_opens: int = 0


class ActivityItemResponse(BaseModel):
    timestamp: datetime
    source: str  # 'share' | 'room'
    event_type: str
    document_id: str | None = None
    document_name: str | None = None
    room_id: str | None = None
    room_name: str | None = None
    page_number: int | None = None
    actor: str | None = None


class NdaPolicySummaryResponse(BaseModel):
    scope_type: str
    scope_id: str
    scope_name: str | None = None
    version: int
    title: str | None = None
    content_type: str
    require_scroll: bool
    require_typed_signature: bool
    acceptance_count: int = 0
    updated_at: datetime

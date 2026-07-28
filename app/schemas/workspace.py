from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from typing import Literal, Optional


class ProductEventRequest(BaseModel):
    event_name: Literal[
        "onboarding_shown",
        "onboarding_step_clicked",
        "first_document_uploaded",
        "first_room_created",
        "first_share_created",
        "first_recipient_viewed",
        "onboarding_dismissed",
        "onboarding_completed",
    ]
    step: Optional[
        Literal["upload_document", "create_room", "create_share", "view_activity"]
    ] = None


class WorkspaceSummaryResponse(BaseModel):
    documents: int = 0
    groups: int = 0
    active_links: int = 0
    external_recipients: int = 0
    document_opens: int = 0
    onboarding_complete: bool = False


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

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NdaPolicyView(BaseModel):
    """NDA policy metadata shown to a recipient (no admin-only fields)."""

    scope_type: str
    scope_id: str
    version: int
    title: str | None = None
    content_type: str  # 'text' | 'pdf'
    require_scroll: bool = True
    require_typed_signature: bool = True


class NdaStatusResponse(BaseModel):
    """Whether an NDA gates a scope and whether the caller has accepted it."""

    required: bool = False
    accepted: bool = True
    policy: NdaPolicyView | None = None
    # Inline text for content_type == 'text'; PDF is fetched via the pdf endpoint.
    text_body: str | None = None
    pdf_available: bool = False


class NdaAcceptRequest(BaseModel):
    scope_type: str  # 'room' | 'document'
    scope_id: str
    typed_name: str = ""
    scroll_confirmed: bool = False
    checkbox_confirmed: bool = False


class NdaAcceptResponse(BaseModel):
    accepted: bool
    scope_type: str
    scope_id: str
    version: int
    accepted_at: datetime


class SetNdaTextRequest(BaseModel):
    title: str | None = None
    text_body: str
    require_scroll: bool = True
    require_typed_signature: bool = True


class NdaPolicyAdminView(BaseModel):
    scope_type: str
    scope_id: str
    version: int
    title: str | None = None
    content_type: str
    require_scroll: bool
    require_typed_signature: bool
    active: bool
    has_pdf: bool = False
    updated_at: datetime


class NdaAcceptanceRecordView(BaseModel):
    id: str
    scope_type: str
    scope_id: str
    nda_version: int
    subject_kind: str
    subject_id: str
    presented_email: str | None = None
    typed_name: str
    scroll_confirmed: bool
    checkbox_confirmed: bool
    accepted_at: datetime

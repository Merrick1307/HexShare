from __future__ import annotations

from pydantic import BaseModel, Field


class ShareLinkInspectionResponse(BaseModel):
    tenant: str
    document: str
    document_name: str
    mime_type: str
    size: int
    link: str
    permissions: dict[str, bool] = Field(default_factory=dict)
    require_email: bool = False
    allowed_emails: list[str] = Field(default_factory=list)
    revoked: bool = False
    expired: bool = False


class CreateViewSessionRequest(BaseModel):
    email: str | None = None


class CreateViewSessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    document_id: str
    document_name: str
    mime_type: str
    size: int
    link_id: str
    permissions: dict[str, bool] = Field(default_factory=dict)
    content_path: str
    download_path: str | None = None
    events_path: str
    watermark_text: str | None = None
    inline_view_supported: bool = True
    view_kind: str = "unsupported"
    view_reason: str | None = None


class ViewerHeartbeatRequest(BaseModel):
    page_number: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)

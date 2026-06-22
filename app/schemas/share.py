from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ShareLinkResponse(BaseModel):
    id: str
    tenant_id: str
    document_id: str
    jti: str
    expires_at: datetime
    can_download: bool = False
    can_print: bool = False
    require_email: bool = False
    allowed_emails: list[str] = Field(default_factory=list)
    access_mode: str = "anonymous"
    bound_email_normalized: str | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    created_by: str
    share_token: str
    share_path: str

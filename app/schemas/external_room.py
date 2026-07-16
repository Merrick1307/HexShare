from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.nda import NdaStatusResponse


class ProvisionExternalRoomAccessResponse(BaseModel):
    external_party_id: str
    display_name: str | None = None
    email: str
    grant_id: str
    room_id: str
    invite_token: str
    invite_path: str
    invite_expires_at: datetime
    can_download: bool = False
    can_print: bool = False


class ExternalRoomGrantResponse(BaseModel):
    grant_id: str
    external_party_id: str
    display_name: str | None = None
    email: str
    room_id: str
    can_download: bool = False
    can_print: bool = False
    revoked_at: datetime | None = None
    expires_at: datetime | None = None
    granted_at: datetime


class ExternalRoomInviteInspectionResponse(BaseModel):
    room_id: str
    room_name: str
    email: str
    display_name: str | None = None
    can_download: bool = False
    can_print: bool = False
    expires_at: datetime


class CreateExternalRoomSessionRequest(BaseModel):
    email: str


class ExternalRoomSessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int
    token_type: str = "Bearer"
    room_id: str
    room_name: str
    display_name: str | None = None
    email: str


class ExternalRoomContextResponse(BaseModel):
    room_id: str
    room_name: str
    display_name: str | None = None
    email: str
    can_download: bool = False
    can_print: bool = False
    nda: NdaStatusResponse | None = None


class ExternalRoomDocumentSessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    room_id: str
    document_id: str
    document_name: str
    mime_type: str
    size: int
    permissions: dict[str, bool]
    content_path: str
    download_path: str | None = None
    watermark_text: str | None = None
    inline_view_supported: bool = True
    view_kind: str = "unsupported"
    view_reason: str | None = None
    page_count: int | None = None
    page_image_path_template: str | None = None

from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field


class CreateRoomSectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RenameRoomSectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ReorderRoomSectionsRequest(BaseModel):
    section_ids: list[str]


class ReorderRoomDocumentsRequest(BaseModel):
    section_id: str | None = None
    document_ids: list[str]


class PlaceDocumentRequest(BaseModel):
    room_id: str
    section_id: str | None = None
    position: int | None = Field(default=None, ge=0)


class ReissueInvitationRequest(BaseModel):
    delivery: Literal["email", "return_link"]


class ReissueInvitationResponse(BaseModel):
    grant_id: str
    invite_path: str
    invite_expires_at: datetime
    email_sent: bool
    resend_available_at: datetime

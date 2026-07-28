from __future__ import annotations

from pydantic import BaseModel, Field


class InitiateUploadRequest(BaseModel):
    filename: str
    content_type: str
    size: int = Field(ge=1)
    expires_in: int = Field(default=900, ge=60, le=3600)


class InitiateUploadResponse(BaseModel):
    document_id: str
    object_key: str
    method: str
    upload_url: str
    expires_in: int
    required_headers: dict[str, str] = Field(default_factory=dict)
    required_form_fields: dict[str, str] = Field(default_factory=dict)
    protection: dict[str, object]


class CompleteUploadRequest(BaseModel):
    document_id: str
    object_key: str
    name: str
    mime_type: str
    size: int = Field(ge=1)
    etag: str | None = None
    room_id: str | None = None
    room_section_id: str | None = None


class DownloadUrlResponse(BaseModel):
    document_id: str
    download_url: str
    expires_in: int

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class InitiateUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    size: int = Field(..., ge=0)
    expires_in: int = Field(default=900, ge=60, le=3600)


class InitiateUploadResponse(BaseModel):
    document_id: str
    object_key: str
    method: str = "PUT"
    upload_url: str
    expires_in: int
    required_headers: Dict[str, str] = Field(default_factory=dict)


class CompleteUploadRequest(BaseModel):
    document_id: str
    object_key: str
    name: str = Field(..., min_length=1)
    mime_type: str = Field(..., min_length=1)
    size: int = Field(..., ge=0)
    etag: Optional[str] = None


class DownloadUrlResponse(BaseModel):
    document_id: str
    download_url: str
    expires_in: int

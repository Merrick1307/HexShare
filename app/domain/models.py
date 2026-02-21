"""
Pydantic domain models for HexShare.

These classes represent persisted entities in the HexShare system.  They
use Pydantic's BaseModel for type validation and (de)serialisation.  The
models here intentionally avoid any business logic; they are simple
containers for data.  Business rules live in services and domain logic.

If your environment doesn't include Pydantic, install it with
``pip install pydantic``.  HexShare's domain models can be converted to
and from dictionaries for storage or network transport.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class EventType(str, Enum):
    """Enumeration of visitor event types.

    ``open``
        The document viewer was opened.

    ``page_view``
        A page of the document was viewed; the payload should include
        ``page_number`` and optionally ``duration_ms``.

    ``heartbeat``
        A periodic signal that the viewer is still active on the page.

    ``close``
        The viewer was closed.

    ``download_attempt``
        The visitor attempted to download the document.

    ``blocked``
        The viewer attempted an action that was not permitted.
    """

    OPEN = "open"
    PAGE_VIEW = "page_view"
    HEARTBEAT = "heartbeat"
    CLOSE = "close"
    DOWNLOAD_ATTEMPT = "download_attempt"
    BLOCKED = "blocked"


class Document(BaseModel):
    """Metadata about an uploaded document.

    Attributes
    ----------
    id:
        Unique identifier for the document.  In a production system this
        might be a UUID.
    tenant_id:
        Identifier of the tenant (workspace) that owns the document.
    name:
        Human readable file name.
    mime_type:
        The MIME type of the stored document (e.g. ``application/pdf``).
    size:
        Size of the document in bytes.
    storage_key:
        Key used to locate the document in object storage (e.g. S3).
    created_at:
        Timestamp of when the document was created.
    created_by:
        Identifier of the user who uploaded the document (could be a
        service account).
    """

    id: str
    tenant_id: str
    name: str
    mime_type: str
    size: int
    storage_key: str
    created_at: datetime
    created_by: str


class ShareLink(BaseModel):
    """Represents a shareable link to a document.

    Attributes
    ----------
    id:
        Unique identifier for the share link; often used as the token
        ``jti`` claim.
    tenant_id:
        Tenant that owns the document and share link.
    document_id:
        The document this link refers to.
    jti:
        Unique token identifier embedded in the JWT.  Can be used for
        revocation tracking.
    expires_at:
        When the share link should no longer be valid.
    can_download:
        Whether downloading the original file is permitted.
    can_print:
        Whether printing is allowed.
    require_email:
        If ``True``, visitors must provide an email address before
        viewing.
    allowed_emails:
        Optional list of emails allowed to access the document; empty
        means any email can access.
    revoked_at:
        When the link was revoked.  ``None`` if still active.
    created_at:
        Time the link was created.
    created_by:
        Identifier of the user who created the link.
    """

    id: str
    tenant_id: str
    document_id: str
    jti: str
    expires_at: datetime
    can_download: bool = False
    can_print: bool = False
    require_email: bool = False
    allowed_emails: Optional[List[str]] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    created_by: str

    @validator("allowed_emails", pre=True, always=True)
    def default_allowed_emails(cls, v):  # type: ignore[override]
        return v or []


class VisitorSession(BaseModel):
    """Represents a visitor's session on a share link.

    The visitor may be anonymous or identified by email depending on the
    link's configuration.  IP and user agent hashes are used for basic
    anomaly detection without storing raw PII.
    """

    id: str
    tenant_id: str
    share_link_id: str
    visitor_id: Optional[str] = None
    ip_hash: Optional[str] = None
    ua_hash: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None


class ViewEvent(BaseModel):
    """Event emitted when a visitor interacts with a document.

    ``event_type`` describes the interaction and is backed by the
    :class:`EventType` enumeration.  ``page_number`` and ``duration_ms``
    are only applicable to ``page_view`` events.
    """

    id: str
    tenant_id: str
    document_id: str
    share_link_id: str
    visitor_session_id: str
    event_type: EventType
    page_number: Optional[int] = None
    duration_ms: Optional[int] = None
    timestamp: datetime

    @validator("page_number", always=True)
    def validate_page_number(cls, v, values):  # type: ignore[override]
        event_type = values.get("event_type")
        if event_type == EventType.PAGE_VIEW and v is None:
            raise ValueError("page_number is required for page_view events")
        return v

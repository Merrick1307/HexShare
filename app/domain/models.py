"""
Pydantic domain models for HexShare.

These classes represent persisted entities in the HexShare system.  They
use Pydantic's BaseModel for type validation and (de)serialisation.  The
models here intentionally avoid any business logic; they are simple
containers for data.  Business rules live in services and domain logic.

If your environment doesn't include Pydantic, install it with
``poetry add pydantic``.  HexShare's domain models can be converted to
and from dictionaries for storage or network transport.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator, validator

from app.core.document_type_policy import describe_document_protection


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


class ExternalPartyStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


class ExternalAccessResourceType(str, Enum):
    DOCUMENT = "document"
    ROOM = "room"


class ExternalAccessGrantType(str, Enum):
    LINK = "link"
    PROVISIONED = "provisioned"


class ShareLinkAccessMode(str, Enum):
    ANONYMOUS = "anonymous"
    IDENTIFIED = "identified"


class ExternalRoomEventType(str, Enum):
    ROOM_OPEN = "room_open"
    DOCUMENT_LIST = "document_list"
    DOCUMENT_VIEW_OPEN = "document_view_open"
    DOCUMENT_PAGE_VIEW = "document_page_view"
    DOCUMENT_VIEW_CLOSE = "document_view_close"
    DOCUMENT_DOWNLOAD = "document_download"
    NDA_ACCEPTED = "nda_accepted"
    ROOM_CLOSE = "room_close"


class NdaScopeType(str, Enum):
    ROOM = "room"
    DOCUMENT = "document"


class NdaContentType(str, Enum):
    TEXT = "text"
    PDF = "pdf"


class NdaSubjectKind(str, Enum):
    EXTERNAL_PARTY = "external_party"
    VISITOR_EMAIL = "visitor_email"
    VISITOR_SESSION = "visitor_session"


class DocumentProtection(BaseModel):
    profile: str
    label: str
    inline_view_supported: bool
    watermark_mode: Optional[str] = None
    page_activity: bool = False
    download_required: bool = False
    reason: Optional[str] = None


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
    room_id: Optional[str] = None  # NULL = ungrouped (uses document_permissions). Otherwise: IAM resource id (e.g. dcgrp_...).
    room_section_id: Optional[str] = None
    room_position: int = 0
    protection: Optional[DocumentProtection] = None

    @model_validator(mode="before")
    @classmethod
    def add_protection_descriptor(cls, values):  # type: ignore[override]
        if not isinstance(values, dict):
            return values
        values = dict(values)
        if values.get("protection") is None:
            descriptor = describe_document_protection(
                str(values.get("name") or ""),
                values.get("mime_type"),
            )
            values["protection"] = descriptor.as_dict()
        return values


class DocumentGroup(BaseModel):
    """A room/space that groups documents under a single IAM-managed resource.

    The ``id`` field is the same opaque identifier registered as a resource
    in the IAM provider, allowing JWT policy claims of the form
    ``{"dcgrp_<id>": <bitmask>}`` to gate access to every document with a
    matching ``room_id``.
    """

    id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    created_by: str
    created_at: datetime


class RoomSection(BaseModel):
    id: str
    tenant_id: str
    room_id: str
    name: str = Field(min_length=1, max_length=120)
    position: int = Field(ge=0)
    created_by: str
    created_at: datetime
    updated_at: datetime


class DocumentPermission(BaseModel):
    """Instance-level permission grant for an ungrouped document.

    Only used for documents whose ``room_id`` is ``None``. Grouped
    documents inherit access from their parent room via the JWT.
    """

    document_id: str
    tenant_id: str
    user_id: str
    permissions: int  # ResourceAction bitmask
    granted_by: str
    granted_at: datetime


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
    external_access_grant_id: Optional[str] = None
    access_mode: ShareLinkAccessMode = ShareLinkAccessMode.ANONYMOUS
    bound_email_normalized: Optional[str] = None
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
    external_party_id: Optional[str] = None
    external_access_grant_id: Optional[str] = None
    presented_email: Optional[str] = None
    identity_source: Optional[str] = None
    ip_hash: Optional[str] = None
    ua_hash: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None


class ExternalParty(BaseModel):
    id: str
    tenant_id: str
    display_name: Optional[str] = None
    status: ExternalPartyStatus = ExternalPartyStatus.ACTIVE
    created_by: str
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None


class ExternalPartyEmail(BaseModel):
    id: str
    tenant_id: str
    external_party_id: str
    email_normalized: str
    email_original: str
    is_primary: bool = True
    verified_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime


class ExternalAccessGrant(BaseModel):
    id: str
    tenant_id: str
    external_party_id: str
    resource_type: ExternalAccessResourceType
    resource_id: str
    grant_type: ExternalAccessGrantType
    permissions: int = 0
    can_download: bool = False
    can_print: bool = False
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    granted_by: str
    granted_at: datetime
    updated_at: datetime
    invite_version: int = 1
    last_invited_at: Optional[datetime] = None


class ExternalRoomSession(BaseModel):
    id: str
    tenant_id: str
    external_party_id: str
    external_access_grant_id: str
    room_id: str
    permissions: int = 0
    presented_email: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    ip_hash: Optional[str] = None
    ua_hash: Optional[str] = None


class ExternalRoomEvent(BaseModel):
    id: str
    tenant_id: str
    external_room_session_id: str
    room_id: str
    event_type: ExternalRoomEventType
    document_id: Optional[str] = None
    page_number: Optional[int] = None
    duration_ms: Optional[int] = None
    timestamp: datetime

    @validator("page_number", always=True)
    def validate_page_number(cls, v, values):  # type: ignore[override]
        event_type = values.get("event_type")
        if event_type == ExternalRoomEventType.DOCUMENT_PAGE_VIEW and v is None:
            raise ValueError("page_number is required for document_page_view events")
        return v


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


class NdaPolicy(BaseModel):
    """An NDA attached to a room (document group) or an individual document.

    Exactly one active policy exists per ``(tenant, scope_type, scope_id)``.
    ``version`` is bumped whenever the content changes, which invalidates prior
    acceptances and forces recipients to re-accept.
    """

    id: str
    tenant_id: str
    scope_type: NdaScopeType
    scope_id: str
    version: int = 1
    title: Optional[str] = None
    content_type: NdaContentType = NdaContentType.TEXT
    text_body: Optional[str] = None
    text_storage_key: Optional[str] = None
    pdf_storage_key: Optional[str] = None
    require_scroll: bool = True
    require_typed_signature: bool = True
    active: bool = True
    created_by: str
    created_at: datetime
    updated_at: datetime


class NdaAcceptance(BaseModel):
    """An immutable record that a subject accepted a specific NDA version."""

    id: str
    tenant_id: str
    nda_policy_id: str
    scope_type: NdaScopeType
    scope_id: str
    nda_version: int
    subject_kind: NdaSubjectKind
    subject_id: str
    external_party_id: Optional[str] = None
    presented_email: Optional[str] = None
    typed_name: str
    scroll_confirmed: bool
    checkbox_confirmed: bool
    session_id: Optional[str] = None
    ip_hash: Optional[str] = None
    ua_hash: Optional[str] = None
    accepted_at: datetime

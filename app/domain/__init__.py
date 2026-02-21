"""
Domain models for HexShare.

This package defines the core entities used throughout HexShare.  The
models are built using ``pydantic``'s BaseModel for validation and
serialisation.  They represent persisted data structures but do not
contain business logic; all behaviour is implemented in services.

Key entities include:

* :class:`Document` – metadata about an uploaded document.
* :class:`ShareLink` – a tokenised link granting access to a document.
* :class:`VisitorSession` – an anonymous visitor's session on a share link.
* :class:`ViewEvent` – events emitted when visitors view or interact with
  a document.

"""

from .models import Document, ShareLink, VisitorSession, ViewEvent, EventType

__all__ = [
    "Document",
    "ShareLink",
    "VisitorSession",
    "ViewEvent",
    "EventType",
]

"""Email clients for various transactional email providers."""
from __future__ import annotations

from app.adapters.email.clients.base import EmailClient
from app.adapters.email.clients.sendbyte_client import SendByteClient

__all__ = [
    "EmailClient",
    "SendByteClient",
]

"""Email adapters."""
from __future__ import annotations

from app.adapters.email.smtp_adapter import SmtpEmailAdapter
from app.adapters.email.transactional_adapter import TransactionalEmailAdapter

__all__ = [
    "SmtpEmailAdapter",
    "TransactionalEmailAdapter",
]

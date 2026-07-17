"""No-op email adapter for testing.

This adapter implements EmailNotificationPort but does nothing.
Useful for tests or local development where email sending is not required.
"""
from __future__ import annotations

from typing import List

from app.ports.email_notification_port import EmailNotificationPort, EmailMessage


class NoopEmailAdapter(EmailNotificationPort):
    """No-op email adapter that does nothing."""

    async def send_email(self, message: EmailMessage) -> str:
        """Pretend to send an email."""
        return f"noop-{message.to}"

    async def send_bulk_email(self, messages: List[EmailMessage]) -> List[str]:
        """Pretend to send multiple emails."""
        return [f"noop-{msg.to}" for msg in messages]

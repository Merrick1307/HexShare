"""Transactional email adapter using pluggable email clients.

This adapter routes to the appropriate transactional email provider client.
Providers are loaded from environment:
- EMAIL_PROVIDER: Provider name (e.g., "sendbyte")
- Provider-specific credentials (EMAIL_PROVIDER_API_KEY, etc.)

Clients implement the EmailClient interface and handle provider-specific
API differences. Add new providers by creating a client in app/adapters/email/clients/.
"""
from __future__ import annotations

from typing import List
import os

from app.ports.email_notification_port import (
    EmailNotificationPort,
    EmailMessage,
    EmailSendError,
)
from app.adapters.email.clients import EmailClient, SendByteClient


class TransactionalEmailAdapter(EmailNotificationPort):
    """Transactional email adapter with pluggable provider clients."""

    def __init__(self, client: EmailClient = None):
        """Initialize with explicit client or auto-detect from environment."""
        if client:
            self.client = client
        else:
            self.client = self._create_client_from_env()

    def _create_client_from_env(self) -> EmailClient:
        """Create email client based on environment variable."""
        provider = os.getenv("EMAIL_PROVIDER", "sendbyte").lower()

        if provider == "sendbyte":
            return SendByteClient()
        else:
            raise ValueError(
                f"Unsupported EMAIL_PROVIDER: {provider}. "
                f"Supported: sendbyte. "
                f"Add new providers in app/adapters/email/clients/"
            )

    async def send_email(self, message: EmailMessage) -> str:
        """Send a single email."""
        try:
            return await self.client.send_email(message)
        except Exception as e:
            raise EmailSendError(f"Failed to send email: {str(e)}") from e

    async def send_bulk_email(self, messages: List[EmailMessage]) -> List[str]:
        """Send multiple emails."""
        try:
            return await self.client.send_bulk_email(messages)
        except Exception as e:
            raise EmailSendError(f"Failed to send bulk email: {str(e)}") from e

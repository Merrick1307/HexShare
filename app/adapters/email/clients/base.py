"""Base email client interface.

All transactional email providers implement this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.ports.email_notification_port import EmailMessage


class EmailClient(ABC):
    """Abstract base class for email service clients."""

    @abstractmethod
    async def send_email(self, message: EmailMessage) -> str:
        """Send a single email.

        Returns
        -------
        str
            Message ID from the provider.
        """
        ...

    @abstractmethod
    async def send_bulk_email(self, messages: List[EmailMessage]) -> List[str]:
        """Send multiple emails.

        Returns
        -------
        List[str]
            Message IDs for each sent email.
        """
        ...

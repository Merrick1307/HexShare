"""Email notification port interface.

The email notification port is responsible for sending emails for
application events (NDA acceptances, document shares, invitations, etc).
Implementations can use various backends: SMTP (FastMail), transactional
email services (SendGrid, Brevo), or mock for testing.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EmailMessage:
    """Email message to send."""
    
    to: str
    subject: str
    body: str
    html_body: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    reply_to: Optional[str] = None
    template_id: Optional[str] = None
    template_vars: Optional[dict] = None


class EmailNotificationPort(ABC):
    """Abstract base class for sending email notifications."""

    @abstractmethod
    async def send_email(self, message: EmailMessage) -> str:
        """Send an email message.

        Parameters
        ----------
        message:
            EmailMessage containing recipient, subject, and body.

        Returns
        -------
        str
            Message ID or delivery ID from the email service.
            
        Raises
        ------
        EmailSendError
            If email fails to send.
        """
        ...

    @abstractmethod
    async def send_bulk_email(self, messages: List[EmailMessage]) -> List[str]:
        """Send multiple email messages.

        Parameters
        ----------
        messages:
            List of EmailMessage objects to send.

        Returns
        -------
        List[str]
            List of message IDs for each sent email.
            
        Raises
        ------
        EmailSendError
            If any email fails to send.
        """
        ...


class EmailSendError(Exception):
    """Raised when email sending fails."""
    pass

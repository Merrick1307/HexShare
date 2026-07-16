"""SMTP email adapter using FastMail.

This adapter sends emails via SMTP using FastMail as the mail server.
Configure via environment variables:
- SMTP_HOST: SMTP server hostname (default: smtp.fastmail.com)
- SMTP_PORT: SMTP port (default: 587)
- SMTP_USER: SMTP username
- SMTP_PASSWORD: SMTP password
- SMTP_FROM_EMAIL: Default sender email address
- SMTP_FROM_NAME: Default sender name
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List
import os

from app.ports.email_notification_port import (
    EmailNotificationPort,
    EmailMessage,
    EmailSendError,
)


class SmtpEmailAdapter(EmailNotificationPort):
    """SMTP email adapter for FastMail."""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
        from_email: str = None,
        from_name: str = None,
    ):
        self.host = host or os.getenv("SMTP_HOST", "smtp.fastmail.com")
        self.port = port or int(os.getenv("SMTP_PORT", "587"))
        self.username = username or os.getenv("SMTP_USER")
        self.password = password or os.getenv("SMTP_PASSWORD")
        self.from_email = from_email or os.getenv("SMTP_FROM_EMAIL")
        self.from_name = from_name or os.getenv("SMTP_FROM_NAME", "HexShare")

        if not all([self.username, self.password, self.from_email]):
            raise ValueError(
                "SMTP credentials not configured. Set SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL"
            )

    async def send_email(self, message: EmailMessage) -> str:
        """Send a single email via SMTP."""
        try:
            msg = self._build_message(message)
            server = smtplib.SMTP(self.host, self.port, timeout=10)
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()
            return msg["Message-ID"]
        except Exception as e:
            raise EmailSendError(f"Failed to send email: {str(e)}") from e

    async def send_bulk_email(self, messages: List[EmailMessage]) -> List[str]:
        """Send multiple emails via SMTP."""
        message_ids = []
        server = smtplib.SMTP(self.host, self.port, timeout=10)
        server.starttls()
        server.login(self.username, self.password)

        try:
            for message in messages:
                try:
                    msg = self._build_message(message)
                    server.send_message(msg)
                    message_ids.append(msg["Message-ID"])
                except Exception as e:
                    raise EmailSendError(f"Failed to send email to {message.to}: {str(e)}") from e
            return message_ids
        finally:
            server.quit()

    def _build_message(self, message: EmailMessage) -> MIMEMultipart:
        """Build MIME message."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = message.subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = message.to

        if message.cc:
            msg["Cc"] = ", ".join(message.cc)
        if message.reply_to:
            msg["Reply-To"] = message.reply_to

        # Attach plain text body
        msg.attach(MIMEText(message.body, "plain"))

        # Attach HTML body if provided
        if message.html_body:
            msg.attach(MIMEText(message.html_body, "html"))

        return msg

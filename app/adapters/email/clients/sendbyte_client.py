"""SendByte email client.

SendByte transactional email service client.
Docs: https://www.sendbyte.com/api

Configure via environment variables:
- SENDBYTE_API_KEY: SendByte API key
- SENDBYTE_API_URL: SendByte API endpoint (default: https://api.sendbyte.com/v1)
- SENDBYTE_FROM_EMAIL: Default sender email
- SENDBYTE_FROM_NAME: Default sender name
"""
from __future__ import annotations

from typing import List
import os
import httpx

from app.adapters.email.clients.base import EmailClient
from app.ports.email_notification_port import EmailMessage, EmailSendError


class SendByteClient(EmailClient):
    """SendByte transactional email client."""

    def __init__(
        self,
        api_key: str = None,
        api_url: str = None,
        from_email: str = None,
        from_name: str = None,
    ):
        self.api_key = api_key or os.getenv("SENDBYTE_API_KEY")
        self.api_url = api_url or os.getenv("SENDBYTE_API_URL", "https://api.sendbyte.africa/v1")
        self.from_email = from_email or os.getenv("SENDBYTE_FROM_EMAIL")
        self.from_name = from_name or os.getenv("SENDBYTE_FROM_NAME", "HexShare")

        if not self.api_key or not self.from_email:
            raise ValueError(
                "SendByte credentials not configured. Set SENDBYTE_API_KEY and SENDBYTE_FROM_EMAIL"
            )

    async def send_email(self, message: EmailMessage) -> str:
        """Send a single email via SendByte."""
        payload = self._build_payload(message)
        print(f"[SendByte] Sending email payload: {payload}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/emails",
                    json=payload,
                    headers=self._get_headers(),
                    timeout=10,
                )
                print(f"[SendByte] Response status: {response.status_code}")
                print(f"[SendByte] Response body: {response.text}")
                response.raise_for_status()
                data = response.json()
                return data.get("id", "sent")
        except httpx.HTTPError as e:
            print(f"[SendByte] HTTP Error: {e}")
            raise EmailSendError(f"SendByte API error: {str(e)}") from e

    async def send_bulk_email(self, messages: List[EmailMessage]) -> List[str]:
        """Send multiple emails via SendByte."""
        message_ids = []
        async with httpx.AsyncClient() as client:
            for message in messages:
                try:
                    payload = self._build_payload(message)
                    response = await client.post(
                        f"{self.api_url}/send",
                        json=payload,
                        headers=self._get_headers(),
                        timeout=10,
                    )
                    response.raise_for_status()
                    data = response.json()
                    message_ids.append(data.get("message_id", "sent"))
                except httpx.HTTPError as e:
                    raise EmailSendError(f"SendByte API error sending to {message.to}: {str(e)}") from e
        return message_ids

    def _get_headers(self) -> dict:
        """Get authorization headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, message: EmailMessage) -> dict:
        """Build SendByte API payload."""
        payload = {
            "from": f"{self.from_name} <{self.from_email}>",
            "to": message.to,
            "subject": message.subject,
        }

        # SendByte Africa requires html, use html_body if available, otherwise use body as html
        if message.html_body:
            payload["html"] = message.html_body
        elif message.body:
            payload["html"] = message.body

        return payload

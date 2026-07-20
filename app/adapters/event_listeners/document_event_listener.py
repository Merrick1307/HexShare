"""Document event listener for sending email notifications.

This listener subscribes to document-related events from the event bus
and sends email notifications (share links, access changes, etc).
"""
from __future__ import annotations

from typing import Any, Dict

from app.ports.email_notification_port import EmailNotificationPort
from app.ports.event_bus_port import EventBusPort
from app.adapters.email.template_loader import EmailTemplateLoader


class DocumentEventListener:
    """Listen to document events and send notifications."""

    def __init__(
        self,
        event_bus: EventBusPort,
        email_service: EmailNotificationPort,
        template_loader: EmailTemplateLoader = None,
    ):
        self.event_bus = event_bus
        self.email_service = email_service
        self.template_loader = template_loader or EmailTemplateLoader()

    async def handle_document_shared(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Handle document shared event."""
        recipient_email = payload.get("recipient_email")
        document_name = payload.get("document_name")
        shared_by_name = payload.get("shared_by_name") or "Someone on HexShare"

        context = {
            "document_name": document_name,
            "shared_by_name": shared_by_name,
            "recipient_name": payload.get("recipient_name", "User"),
            "access_link": payload.get("access_link"),
            "expires_at": payload.get("expires_at"),
            "message": payload.get("message"),
        }

        message = self.template_loader.create_email_message(
            to=recipient_email,
            subject=f"{shared_by_name} shared '{document_name}' with you",
            template_base="document/shared",
            context=context,
        )
        await self.email_service.send_email(message)

    async def handle_document_accessed(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Handle document accessed/opened event."""
        owner_email = payload.get("owner_email")

        context = {
            "document_name": payload.get("document_name"),
            "accessed_by_name": payload.get("accessed_by_name", "Someone"),
            "owner_name": payload.get("owner_name", "Owner"),
            "accessed_at": payload.get("accessed_at"),
        }

        message = self.template_loader.create_email_message(
            to=owner_email,
            subject=f"{context['accessed_by_name']} viewed {context['document_name']}",
            template_base="document/accessed",
            context=context,
        )
        await self.email_service.send_email(message)

    async def handle_share_link_expired(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Handle share link expired event."""
        recipient_email = payload.get("recipient_email")

        context = {
            "document_name": payload.get("document_name"),
            "recipient_name": payload.get("recipient_name", "User"),
            "owner_name": payload.get("owner_name", "The owner"),
            "expired_at": payload.get("expired_at"),
        }

        message = self.template_loader.create_email_message(
            to=recipient_email,
            subject=f"Access Expired: {context['document_name']}",
            template_base="document/link_expired",
            context=context,
        )
        await self.email_service.send_email(message)

    async def handle_external_room_invited(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Handle external room invited event."""
        recipient_email = payload.get("recipient_email")
        room_name = payload.get("room_name")
        invited_by_name = payload.get("invited_by_name") or "Someone on HexShare"

        context = {
            "room_name": room_name,
            "recipient_name": payload.get("recipient_name", "User"),
            "invited_by_name": invited_by_name,
            "invite_link": payload.get("invite_link"),
            "invite_expires_at": payload.get("invite_expires_at"),
            "can_download": payload.get("can_download", False),
            "can_print": payload.get("can_print", False),
        }

        message = self.template_loader.create_email_message(
            to=recipient_email,
            subject=f"{invited_by_name} invited you to '{room_name}'",
            template_base="external_room/invited",
            context=context,
        )
        await self.email_service.send_email(message)

    async def handle_event(self, event_name: str, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Route events to appropriate handlers."""
        if event_name == "document.shared":
            await self.handle_document_shared(tenant_id, payload)
        elif event_name == "document.accessed":
            await self.handle_document_accessed(tenant_id, payload)
        elif event_name == "share_link.expired":
            await self.handle_share_link_expired(tenant_id, payload)
        elif event_name == "external_room.invited":
            await self.handle_external_room_invited(tenant_id, payload)

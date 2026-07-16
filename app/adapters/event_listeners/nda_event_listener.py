"""NDA event listener for sending email notifications.

This listener subscribes to NDA-related events from the event bus
and sends email notifications to relevant parties.
"""
from __future__ import annotations

from typing import Any, Dict

from app.ports.email_notification_port import EmailNotificationPort
from app.ports.event_bus_port import EventBusPort
from app.adapters.email.template_loader import EmailTemplateLoader


class NdaEventListener:
    """Listen to NDA events and send notifications."""

    def __init__(
        self,
        event_bus: EventBusPort,
        email_service: EmailNotificationPort,
        template_loader: EmailTemplateLoader = None,
    ):
        self.event_bus = event_bus
        self.email_service = email_service
        self.template_loader = template_loader or EmailTemplateLoader()

    async def handle_nda_created(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Handle NDA created event."""
        nda_title = payload.get("title")
        created_by = payload.get("created_by_email")
        admin_emails = payload.get("admin_emails", [])

        context = {
            "nda_id": payload.get("nda_id"),
            "title": nda_title,
            "created_by": created_by,
        }

        for admin_email in admin_emails:
            message = self.template_loader.create_email_message(
                to=admin_email,
                subject=f"New NDA Created: {nda_title}",
                template_base="nda/created",
                context=context,
            )
            await self.email_service.send_email(message)

    async def handle_nda_acceptance_required(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Handle NDA acceptance required event."""
        nda_title = payload.get("title")
        recipient_email = payload.get("recipient_email")

        context = {
            "recipient_name": payload.get("recipient_name", "User"),
            "title": nda_title,
            "deadline": payload.get("deadline"),
            "acceptance_link": payload.get("acceptance_link"),
        }

        message = self.template_loader.create_email_message(
            to=recipient_email,
            subject=f"Action Required: Please Accept {nda_title}",
            template_base="nda/acceptance_required",
            context=context,
        )
        await self.email_service.send_email(message)

    async def handle_nda_accepted(self, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Handle NDA accepted event."""
        recipient_email = payload.get("recipient_email")
        nda_title = payload.get("title")

        context = {
            "recipient_name": payload.get("recipient_name", "User"),
            "title": nda_title,
            "accepted_at": payload.get("accepted_at"),
        }

        message = self.template_loader.create_email_message(
            to=recipient_email,
            subject=f"Confirmation: {nda_title} Accepted",
            template_base="nda/accepted",
            context=context,
        )
        await self.email_service.send_email(message)

    async def handle_event(self, event_name: str, tenant_id: str, payload: Dict[str, Any]) -> None:
        """Route events to appropriate handlers."""
        if event_name == "nda.created":
            await self.handle_nda_created(tenant_id, payload)
        elif event_name == "nda.acceptance_required":
            await self.handle_nda_acceptance_required(tenant_id, payload)
        elif event_name == "nda.accepted":
            await self.handle_nda_accepted(tenant_id, payload)

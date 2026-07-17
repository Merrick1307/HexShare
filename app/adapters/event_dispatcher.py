"""Event dispatcher for registering and dispatching events to listeners.

This module centralizes all event listener registrations and provides
a single point to subscribe all listeners to the event bus.
"""
from __future__ import annotations

from typing import Any, Dict

from app.ports.event_bus_port import EventBusPort
from app.ports.email_notification_port import EmailNotificationPort
from app.adapters.event_listeners import NdaEventListener, DocumentEventListener


class EventDispatcher:
    """Centralized event dispatcher for managing listeners."""

    def __init__(
        self,
        event_bus: EventBusPort,
        email_service: EmailNotificationPort,
    ):
        self.event_bus = event_bus
        self.email_service = email_service

        # Initialize listeners
        self.nda_listener = NdaEventListener(event_bus, email_service)
        self.document_listener = DocumentEventListener(event_bus, email_service)

        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register all event handlers with the event bus."""
        # NDA events
        self.event_bus.subscribe("nda.created", self.nda_listener.handle_event)
        self.event_bus.subscribe("nda.acceptance_required", self.nda_listener.handle_event)
        self.event_bus.subscribe("nda.accepted", self.nda_listener.handle_event)
        self.event_bus.subscribe("nda.rejected", self.nda_listener.handle_event)

        # Document events
        self.event_bus.subscribe("document.shared", self.document_listener.handle_event)
        self.event_bus.subscribe("document.accessed", self.document_listener.handle_event)
        self.event_bus.subscribe("share_link.expired", self.document_listener.handle_event)
        
        # External room events
        self.event_bus.subscribe("external_room.invited", self.document_listener.handle_event)

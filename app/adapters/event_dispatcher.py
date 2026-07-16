"""Event dispatcher for registering and dispatching events to listeners.

This module centralizes all event listener registrations and provides
a single point to subscribe all listeners to the event bus.
"""
from __future__ import annotations

from typing import Any, Dict, List, Callable
import asyncio

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
        self.handlers: Dict[str, List[Callable]] = {}

        # Initialize listeners
        self.nda_listener = NdaEventListener(event_bus, email_service)
        self.document_listener = DocumentEventListener(event_bus, email_service)

        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register all event handlers."""
        # NDA events
        self.register("nda.created", self.nda_listener.handle_event)
        self.register("nda.acceptance_required", self.nda_listener.handle_event)
        self.register("nda.accepted", self.nda_listener.handle_event)
        self.register("nda.rejected", self.nda_listener.handle_event)

        # Document events
        self.register("document.shared", self.document_listener.handle_event)
        self.register("document.accessed", self.document_listener.handle_event)
        self.register("share_link.expired", self.document_listener.handle_event)

    def register(self, event_name: str, handler: Callable) -> None:
        """Register an event handler.

        Parameters
        ----------
        event_name:
            Event name to subscribe to (e.g., "nda.created").
        handler:
            Async callable that handles the event.
        """
        if event_name not in self.handlers:
            self.handlers[event_name] = []
        self.handlers[event_name].append(handler)

    async def dispatch(
        self,
        event_name: str,
        tenant_id: str,
        payload: Dict[str, Any],
    ) -> None:
        """Dispatch an event to all registered handlers.

        Parameters
        ----------
        event_name:
            Event name (e.g., "nda.created").
        tenant_id:
            Tenant/workspace ID for the event.
        payload:
            Event payload containing event data.
        """
        handlers = self.handlers.get(event_name, [])
        if not handlers:
            return

        # Run all handlers concurrently
        tasks = [
            handler(event_name, tenant_id, payload)
            for handler in handlers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any errors but don't raise (event processing shouldn't block)
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                print(f"Error in {handler.__name__} for event {event_name}: {result}")

"""
In-memory event bus adapter.

This adapter implements :class:`~app.ports.EventBusPort` and dispatches
events to registered listeners synchronously. Useful for single-process
deployments where events need to trigger email notifications immediately.
"""
from __future__ import annotations

from typing import Any, Dict, List, Callable
import asyncio

from app.ports.event_bus_port import EventBusPort


class InMemoryEventBus(EventBusPort):
    """In-memory event bus that dispatches to registered handlers."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable) -> None:
        """Subscribe a handler to an event."""
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    async def publish_event(self, tenant_id: str, event_name: str, payload: Dict[str, Any]) -> None:
        """Publish an event to all registered handlers."""
        handlers = self._handlers.get(event_name, [])
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

"""
Event bus port interface.

The event bus is responsible for publishing audit and analytics events
emitted by HexShare.  These events could be consumed by other
services (e.g. analytics pipelines, logging systems).  An event bus
implementation may send messages to Redis Streams, Kafka, an HTTP
endpoint or simply drop them (no‑op).  The interface is minimal to
allow future expansion without breaking implementers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class EventBusPort(ABC):
    """Abstract base class for publishing events."""

    @abstractmethod
    async def publish_event(self, tenant_id: str, event_name: str, payload: Dict[str, Any]) -> None:
        """Publish an event to the bus.

        Parameters
        ----------
        tenant_id:
            The tenant/workspace ID associated with the event.
        event_name:
            A dot‑separated name describing the event (e.g. ``document.created``).
        payload:
            JSON‑serialisable dictionary containing event data.
        """
        ...

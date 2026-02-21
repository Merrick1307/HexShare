"""
No‑op event bus adapter.

This adapter implements :class:`~app.ports.EventBusPort` but
performs no actions.  It is useful for tests or setups where event
publishing is not required.  In a real deployment this should be
replaced with an adapter that sends events to a message broker or
logging system.
"""
from __future__ import annotations

from typing import Any, Dict

from app.ports.event_bus_port import EventBusPort


class NoopEventBus(EventBusPort):
    async def publish_event(self, tenant_id: str, event_name: str, payload: Dict[str, Any]) -> None:
        # Intentionally do nothing
        return None

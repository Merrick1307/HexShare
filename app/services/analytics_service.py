"""
Analytics service.

This service aggregates visitor events to provide high‑level statistics
about document engagement.  For the initial scaffold it exposes a
method that returns counts of unique visitors and total views.  In a
production system this service might compute per‑page heatmaps,
average time on page and other insights.
"""
from __future__ import annotations

from typing import Dict, Iterable

from app.domain import ViewEvent
from app.ports.storage_port import StoragePort


class AnalyticsService:
    """Compute aggregate analytics from raw events."""

    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    async def get_document_metrics(self, *, tenant_id: str, document_id: str) -> Dict[str, int]:
        """Return simple metrics for a document.

        Currently returns ``unique_visitors`` and ``total_views``.  Uses
        the storage port to query persisted events.  Additional metrics
        can be added as needed.
        """
        events: Iterable[ViewEvent] = await self._storage.list_view_events(
            tenant_id=tenant_id, document_id=document_id
        )
        unique_visitors = {e.visitor_session_id for e in events}
        total_views = sum(1 for e in events if e.event_type == e.event_type.PAGE_VIEW)
        return {
            "unique_visitors": len(unique_visitors),
            "total_views": total_views,
        }

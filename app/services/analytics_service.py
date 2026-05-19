"""
Analytics service.

Analytics should reflect the current secure-viewer flow: visitor
sessions represent document views, while page-view events represent
navigation inside a session. This service aggregates both.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable

from app.domain import EventType, ViewEvent, VisitorSession
from app.ports.storage_port import StoragePort


class AnalyticsService:
    """Compute aggregate analytics from visitor sessions and page events."""

    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    async def get_document_metrics(self, *, tenant_id: str, document_id: str) -> Dict[str, Any]:
        """Return document metrics aligned with the current viewer flow."""
        sessions: Iterable[VisitorSession] = await self._storage.list_visitor_sessions(
            tenant_id=tenant_id,
            document_id=document_id,
        )
        events: Iterable[ViewEvent] = await self._storage.list_view_events(
            tenant_id=tenant_id,
            document_id=document_id,
        )

        session_list = list(sessions)
        event_list = list(events)
        unique_visitors = {
            session.visitor_id.strip().lower() if session.visitor_id else session.id
            for session in session_list
        }

        page_view_events = [
            event for event in event_list if event.event_type == EventType.PAGE_VIEW
        ]
        page_stats: dict[int, dict[str, int]] = defaultdict(
            lambda: {"view_count": 0, "total_duration_ms": 0}
        )

        for event in page_view_events:
            if event.page_number is None:
                continue
            stats = page_stats[event.page_number]
            stats["view_count"] += 1
            stats["total_duration_ms"] += max(event.duration_ms or 0, 0)

        pages = [
            {
                "page_number": page_number,
                "view_count": stats["view_count"],
                "total_duration_ms": stats["total_duration_ms"],
                "avg_duration_ms": (
                    stats["total_duration_ms"] // stats["view_count"]
                    if stats["view_count"] > 0
                    else 0
                ),
            }
            for page_number, stats in sorted(page_stats.items())
        ]

        completed_session_durations = [
            max(int((session.ended_at - session.started_at).total_seconds() * 1000), 0)
            for session in session_list
            if session.ended_at is not None
        ]

        return {
            "unique_visitors": len(unique_visitors),
            "total_views": len(session_list),
            "total_sessions": len(session_list),
            "page_views": len(page_view_events),
            "total_time_ms": sum(page["total_duration_ms"] for page in pages),
            "avg_session_duration_ms": (
                sum(completed_session_durations) // len(completed_session_durations)
                if completed_session_durations
                else 0
            ),
            "pages": pages,
        }

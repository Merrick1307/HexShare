"""
Analytics service.

Visitor sessions represent document views, while page-view events represent
navigation inside a session. This service aggregates both.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable

from app.domain import EventType, ExternalRoomEventType, ViewEvent, VisitorSession
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
        external_room_sessions = list(
            await self._storage.list_external_room_sessions(tenant_id=tenant_id)
        )
        external_room_events = list(
            await self._storage.list_external_room_events(
                tenant_id=tenant_id,
                document_id=document_id,
            )
        )

        session_list = list(sessions)
        event_list = list(events)
        external_session_by_id = {session.id: session for session in external_room_sessions}
        unique_visitors = {
            session.visitor_id.strip().lower() if session.visitor_id else session.id
            for session in session_list
        }
        unique_visitors.update(
            (
                external_session_by_id[event.external_room_session_id].presented_email.strip().lower()
                if external_session_by_id.get(event.external_room_session_id)
                else event.external_room_session_id
            )
            for event in external_room_events
            if event.event_type == ExternalRoomEventType.DOCUMENT_VIEW_OPEN
        )

        page_view_events = [
            event for event in event_list if event.event_type == EventType.PAGE_VIEW
        ]
        external_page_view_events = [
            event for event in external_room_events if event.event_type == ExternalRoomEventType.DOCUMENT_PAGE_VIEW
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
        for event in external_page_view_events:
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
        room_view_open_events = {
            (event.external_room_session_id, event.document_id): event
            for event in external_room_events
            if event.event_type == ExternalRoomEventType.DOCUMENT_VIEW_OPEN and event.document_id
        }
        room_view_close_events = {
            (event.external_room_session_id, event.document_id): event
            for event in external_room_events
            if event.event_type == ExternalRoomEventType.DOCUMENT_VIEW_CLOSE and event.document_id
        }
        room_view_count = len(room_view_open_events)
        completed_room_view_durations = [
            max(int((close_event.timestamp - open_event.timestamp).total_seconds() * 1000), 0)
            for key, open_event in room_view_open_events.items()
            if (close_event := room_view_close_events.get(key)) is not None
        ]
        combined_session_durations = completed_session_durations + completed_room_view_durations

        return {
            "unique_visitors": len(unique_visitors),
            "total_views": len(session_list) + room_view_count,
            "total_sessions": len(session_list) + room_view_count,
            "page_views": len(page_view_events) + len(external_page_view_events),
            "total_time_ms": sum(page["total_duration_ms"] for page in pages),
            "avg_session_duration_ms": (
                sum(combined_session_durations) // len(combined_session_durations)
                if combined_session_durations
                else 0
            ),
            "pages": pages,
        }

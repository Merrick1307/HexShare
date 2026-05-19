from __future__ import annotations

from datetime import datetime

import pytest

from app.domain import EventType, ViewEvent, VisitorSession
from app.services.analytics_service import AnalyticsService


class _StorageStub:
    def __init__(self, sessions: list[VisitorSession], events: list[ViewEvent]) -> None:
        self.sessions = sessions
        self.events = events

    async def list_visitor_sessions(self, *, tenant_id: str, document_id: str):
        return self.sessions

    async def list_view_events(self, *, tenant_id: str, document_id: str):
        return self.events


@pytest.mark.asyncio
async def test_get_document_metrics_uses_sessions_for_views_and_builds_page_stats():
    sessions = [
        VisitorSession(
            id="vs_1",
            tenant_id="tenant-1",
            share_link_id="link-1",
            visitor_id="viewer@example.com",
            started_at=datetime(2026, 5, 16, 12, 0, 0),
            ended_at=datetime(2026, 5, 16, 12, 0, 10),
        ),
        VisitorSession(
            id="vs_2",
            tenant_id="tenant-1",
            share_link_id="link-1",
            visitor_id="viewer@example.com",
            started_at=datetime(2026, 5, 16, 12, 5, 0),
            ended_at=datetime(2026, 5, 16, 12, 5, 6),
        ),
        VisitorSession(
            id="vs_3",
            tenant_id="tenant-1",
            share_link_id="link-2",
            visitor_id=None,
            started_at=datetime(2026, 5, 16, 12, 10, 0),
            ended_at=None,
        ),
    ]
    events = [
        ViewEvent(
            id="evt_1",
            tenant_id="tenant-1",
            document_id="doc-1",
            share_link_id="link-1",
            visitor_session_id="vs_1",
            event_type=EventType.OPEN,
            timestamp=datetime(2026, 5, 16, 12, 0, 0),
        ),
        ViewEvent(
            id="evt_2",
            tenant_id="tenant-1",
            document_id="doc-1",
            share_link_id="link-1",
            visitor_session_id="vs_1",
            event_type=EventType.PAGE_VIEW,
            page_number=1,
            duration_ms=4000,
            timestamp=datetime(2026, 5, 16, 12, 0, 2),
        ),
        ViewEvent(
            id="evt_3",
            tenant_id="tenant-1",
            document_id="doc-1",
            share_link_id="link-1",
            visitor_session_id="vs_1",
            event_type=EventType.PAGE_VIEW,
            page_number=2,
            duration_ms=3000,
            timestamp=datetime(2026, 5, 16, 12, 0, 6),
        ),
        ViewEvent(
            id="evt_4",
            tenant_id="tenant-1",
            document_id="doc-1",
            share_link_id="link-1",
            visitor_session_id="vs_2",
            event_type=EventType.PAGE_VIEW,
            page_number=1,
            duration_ms=2000,
            timestamp=datetime(2026, 5, 16, 12, 5, 2),
        ),
        ViewEvent(
            id="evt_5",
            tenant_id="tenant-1",
            document_id="doc-1",
            share_link_id="link-2",
            visitor_session_id="vs_3",
            event_type=EventType.PAGE_VIEW,
            page_number=2,
            duration_ms=None,
            timestamp=datetime(2026, 5, 16, 12, 10, 2),
        ),
    ]

    service = AnalyticsService(_StorageStub(sessions, events))  # type: ignore[arg-type]

    metrics = await service.get_document_metrics(tenant_id="tenant-1", document_id="doc-1")

    assert metrics["unique_visitors"] == 2
    assert metrics["total_views"] == 3
    assert metrics["total_sessions"] == 3
    assert metrics["page_views"] == 4
    assert metrics["total_time_ms"] == 9000
    assert metrics["avg_session_duration_ms"] == 8000
    assert metrics["pages"] == [
        {
            "page_number": 1,
            "view_count": 2,
            "total_duration_ms": 6000,
            "avg_duration_ms": 3000,
        },
        {
            "page_number": 2,
            "view_count": 2,
            "total_duration_ms": 3000,
            "avg_duration_ms": 1500,
        },
    ]

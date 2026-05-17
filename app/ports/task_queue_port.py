from __future__ import annotations

from abc import ABC, abstractmethod


class TaskQueuePort(ABC):
    @abstractmethod
    async def enqueue_prerender_page(
        self,
        *,
        session_id: str,
        page_number: int,
        render_width: int | None,
    ) -> None:
        raise NotImplementedError


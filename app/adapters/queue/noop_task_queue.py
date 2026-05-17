from __future__ import annotations

from app.infra.factories import TaskQueueFactory
from app.ports.task_queue_port import TaskQueuePort


class NoopTaskQueue(TaskQueuePort):
    async def enqueue_prerender_page(
        self,
        *,
        session_id: str,
        page_number: int,
        render_width: int | None,
    ) -> None:
        return None


@TaskQueueFactory.register("noop")
def create_noop_task_queue(**kwargs) -> TaskQueuePort:
    return NoopTaskQueue()


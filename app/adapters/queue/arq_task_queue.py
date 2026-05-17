from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from arq.connections import ArqRedis, RedisSettings, create_pool
except ImportError:
    ArqRedis = None  # type: ignore
    RedisSettings = None  # type: ignore
    create_pool = None  # type: ignore

from app.infra.factories import TaskQueueFactory
from app.ports.task_queue_port import TaskQueuePort


@dataclass(frozen=True)
class _JobNames:
    prerender_page: str = "prerender_page"


class ArqTaskQueue(TaskQueuePort):
    def __init__(self, *, redis_url: str, job_names: _JobNames | None = None) -> None:
        if create_pool is None or RedisSettings is None:
            raise RuntimeError("arq is required for ArqTaskQueue")
        self._redis_url = redis_url
        self._pool: ArqRedis | None = None
        self._job_names = job_names or _JobNames()

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            settings = RedisSettings.from_dsn(self._redis_url)
            self._pool = await create_pool(settings)
        return self._pool

    @staticmethod
    def _build_prerender_job_id(
        *,
        session_id: str,
        page_number: int,
        render_width: int | None,
    ) -> str:
        width_component = "none" if render_width is None else str(render_width)
        return f"prerender:{session_id}:{page_number}:{width_component}"

    async def enqueue_prerender_page(
        self,
        *,
        session_id: str,
        page_number: int,
        render_width: int | None,
    ) -> None:
        pool = await self._get_pool()
        job_id = self._build_prerender_job_id(
            session_id=session_id,
            page_number=page_number,
            render_width=render_width,
        )
        await pool.enqueue_job(
            self._job_names.prerender_page,
            session_id=session_id,
            page_number=page_number,
            render_width=render_width,
            _job_id=job_id,
        )


@TaskQueueFactory.register("arq")
def create_arq_task_queue(**kwargs) -> TaskQueuePort:
    redis_url = kwargs.get("redis_url") or os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is required for arq task queue")
    return ArqTaskQueue(redis_url=redis_url)


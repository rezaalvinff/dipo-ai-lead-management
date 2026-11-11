"""Job queue abstraction.

- ArqJobQueue: production/dev with Docker — jobs go to Redis, the worker runs them.
- InlineJobQueue: runs the job immediately in the same process (tests).
Both run the very same task function (app.workers.tasks).
"""

import logging
import uuid
from typing import TYPE_CHECKING, Protocol

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import JobQueueMode

if TYPE_CHECKING:
    from app.core.context import AppContext

logger = logging.getLogger(__name__)

AI_REPLY_JOB = "generate_ai_reply"


class JobQueue(Protocol):
    async def enqueue_ai_reply(self, message_id: uuid.UUID) -> None: ...

    async def close(self) -> None: ...


class ArqJobQueue:
    def __init__(self, redis_url: str):
        self._redis_settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(self._redis_settings)
        return self._pool

    async def enqueue_ai_reply(self, message_id: uuid.UUID) -> None:
        pool = await self._get_pool()
        # _job_id makes the enqueue idempotent for the same inbound message.
        await pool.enqueue_job(AI_REPLY_JOB, str(message_id), _job_id=f"ai-reply:{message_id}")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()


class InlineJobQueue:
    def __init__(self, ctx: "AppContext"):
        self._ctx = ctx

    async def enqueue_ai_reply(self, message_id: uuid.UUID) -> None:
        from app.workers.tasks import process_ai_reply

        await process_ai_reply(self._ctx, message_id)

    async def close(self) -> None:
        return None


def build_job_queue(ctx: "AppContext") -> JobQueue:
    if ctx.settings.job_queue == JobQueueMode.INLINE:
        return InlineJobQueue(ctx)
    return ArqJobQueue(ctx.settings.redis_url)

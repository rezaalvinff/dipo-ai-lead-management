"""Everything the app and the worker need, built once from Settings."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.adapters.ai.base import AIProvider
from app.adapters.factory import build_ai_provider, build_messaging_provider
from app.adapters.whatsapp.base import MessagingProvider
from app.core.config import Settings
from app.core.database import create_engine, create_session_factory
from app.core.redis import create_redis

if TYPE_CHECKING:
    from app.workers.queue import JobQueue


@dataclass
class AppContext:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    messaging: MessagingProvider
    ai: AIProvider
    queue: "JobQueue" = field(init=False)

    async def close(self) -> None:
        await self.queue.close()
        await self.redis.aclose()
        await self.engine.dispose()


def build_context(settings: Settings) -> AppContext:
    from app.workers.queue import build_job_queue

    engine = create_engine(settings.database_url)
    ctx = AppContext(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        redis=create_redis(settings.redis_url),
        messaging=build_messaging_provider(settings),
        ai=build_ai_provider(settings),
    )
    ctx.queue = build_job_queue(ctx)
    return ctx

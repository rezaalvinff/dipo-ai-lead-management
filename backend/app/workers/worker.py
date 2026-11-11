"""Background worker (ARQ). Start with:  arq app.workers.worker.WorkerSettings"""

import logging
import uuid

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.context import build_context
from app.core.logging import configure_logging
from app.workers.tasks import process_ai_reply

logger = logging.getLogger(__name__)
_settings = get_settings()  # validates safety rules: worker refuses to start if unsafe


async def startup(ctx: dict) -> None:
    configure_logging(_settings.log_level)
    logging.getLogger("arq").propagate = False  # arq prints its own job logs
    ctx["app"] = build_context(_settings)
    logger.info(
        "Worker started env=%s whatsapp=%s ai=%s",
        _settings.app_env,
        _settings.whatsapp_provider,
        _settings.ai_provider,
    )


async def shutdown(ctx: dict) -> None:
    await ctx["app"].close()


async def generate_ai_reply(ctx: dict, message_id: str) -> None:
    await process_ai_reply(ctx["app"], uuid.UUID(message_id))


class WorkerSettings:
    functions = [generate_ai_reply]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    max_tries = 3

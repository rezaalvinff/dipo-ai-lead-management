import logging
import uuid
from typing import TYPE_CHECKING

from app.services.auto_reply_service import AutoReplyService

if TYPE_CHECKING:
    from app.core.context import AppContext

logger = logging.getLogger(__name__)


async def process_ai_reply(ctx: "AppContext", message_id: uuid.UUID) -> None:
    async with ctx.session_factory() as session:
        service = AutoReplyService(
            session, ctx.ai, ctx.messaging, history_limit=ctx.settings.ai_history_limit
        )
        try:
            await service.reply_to(message_id)
        except Exception:
            await session.rollback()
            logger.exception("AI reply failed for message %s", message_id)
            raise

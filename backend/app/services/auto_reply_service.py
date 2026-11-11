import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ai.base import AIProvider, ChatTurn
from app.adapters.whatsapp.base import MessagingProvider
from app.models import Conversation, Message
from app.models.enums import (
    ConversationHandler,
    ConversationStatus,
    MessageDirection,
    SenderType,
)
from app.services.message_service import MessageService

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20


class AutoReplyService:
    """Generate and send the AI reply for one inbound message."""

    def __init__(self, session: AsyncSession, ai: AIProvider, messaging: MessagingProvider):
        self.session = session
        self.ai = ai
        self.messages = MessageService(session, messaging)

    async def reply_to(self, inbound_message_id: uuid.UUID) -> Message | None:
        inbound = await self.session.get(Message, inbound_message_id)
        if inbound is None or inbound.direction != MessageDirection.INBOUND:
            return None
        conversation = await self.session.get(Conversation, inbound.conversation_id)
        if (
            conversation is None
            or conversation.status != ConversationStatus.OPEN
            or conversation.handler != ConversationHandler.AI
        ):
            logger.info("Skip AI reply: conversation not handled by AI")
            return None

        rows = await self.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(HISTORY_LIMIT)
        )
        history = [
            ChatTurn(
                role="contact" if m.direction == MessageDirection.INBOUND else "assistant",
                text=m.content,
            )
            for m in reversed(list(rows))
        ]
        reply = await self.ai.generate_reply(history)
        message = await self.messages.send_outbound(
            conversation, reply.text, sender_type=SenderType.AI
        )
        await self.session.commit()
        return message

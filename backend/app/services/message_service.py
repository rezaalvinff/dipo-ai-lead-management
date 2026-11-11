"""The single place where messages are stored, sent and status-updated.

Used by the simulator AND the WhatsApp Cloud webhook — never duplicated.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.whatsapp.base import (
    InboundMessage,
    MessagingProvider,
    SendResult,
    StatusUpdate,
)
from app.core.errors import AppError
from app.core.safety import RealDeliveryBlockedError
from app.models import Contact, Conversation, Message
from app.models.enums import (
    OUTBOUND_STATUS_RANK,
    MessageDirection,
    MessageStatus,
    ProviderName,
    SenderType,
)

logger = logging.getLogger(__name__)


class MessageService:
    def __init__(self, session: AsyncSession, messaging: MessagingProvider | None = None):
        self.session = session
        self.messaging = messaging

    async def record_inbound(
        self, conversation: Conversation, inbound: InboundMessage
    ) -> Message | None:
        """Store an incoming message. Returns None if it was already stored (duplicate)."""
        message_id = await self.session.scalar(
            insert(Message)
            .values(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                sender_type=SenderType.CONTACT,
                provider=inbound.provider,
                message_type=inbound.message_type,
                content=inbound.text,
                provider_message_id=inbound.provider_message_id,
                status=MessageStatus.RECEIVED,
                raw_payload=inbound.raw,
                sent_at=inbound.timestamp,
            )
            .on_conflict_do_nothing(index_elements=[Message.provider_message_id])
            .returning(Message.id)
        )
        if message_id is None:
            logger.info("Duplicate inbound message ignored: %s", inbound.provider_message_id)
            return None

        now = datetime.now(UTC)
        conversation.last_message_at = now
        conversation.last_inbound_at = now
        conversation.unread_count = (conversation.unread_count or 0) + 1
        return await self.session.get(Message, message_id)

    async def send_outbound(
        self,
        conversation: Conversation,
        text: str,
        *,
        sender_type: SenderType,
        sender_user_id: uuid.UUID | None = None,
    ) -> Message:
        """Store an outgoing message, hand it to the active provider, record the result."""
        if self.messaging is None:
            raise RuntimeError("MessageService needs a MessagingProvider to send")
        if getattr(self.messaging, "name", None) == ProviderName.WHATSAPP_CLOUD:
            last_inbound = conversation.last_inbound_at
            if (
                last_inbound is None
                or datetime.now(UTC) - last_inbound > timedelta(hours=24)
            ):
                raise AppError(
                    "Jendela layanan 24 jam telah berakhir. Gunakan template WhatsApp "
                    "yang disetujui Meta.",
                    code="WHATSAPP_TEMPLATE_REQUIRED",
                )
        contact = await self.session.get(Contact, conversation.contact_id)
        if contact is None:
            raise RuntimeError("Conversation has no contact")

        message = Message(
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            provider=self.messaging.name,
            message_type="text",
            content=text,
            status=MessageStatus.QUEUED,
        )
        self.session.add(message)
        await self.session.flush()

        if contact.opted_out:
            message.status = MessageStatus.FAILED
            message.error_detail = "Contact opted out"
            return message

        try:
            result = await self.messaging.send_text(contact.phone_number, text)
        except RealDeliveryBlockedError as exc:
            logger.warning("Outbound blocked by safety guard: %s", exc)
            message.status = MessageStatus.FAILED
            message.error_detail = str(exc)
            return message

        now = datetime.now(UTC)
        message.status = result.status
        message.error_detail = result.error
        if result.provider_message_id:
            message.provider_message_id = result.provider_message_id
        if result.status == MessageStatus.SENT:
            message.sent_at = now
        conversation.last_message_at = now
        return message


    async def _send_special(
        self,
        conversation: Conversation,
        *,
        message_type: str,
        content: str,
        sender_type: SenderType,
        sender_user_id: uuid.UUID | None,
        send: Callable[[str], Awaitable[SendResult]],
    ) -> Message:
        if self.messaging is None:
            raise RuntimeError("MessageService needs a MessagingProvider to send")
        contact = await self.session.get(Contact, conversation.contact_id)
        if contact is None:
            raise RuntimeError("Conversation has no contact")
        message = Message(
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            provider=self.messaging.name,
            message_type=message_type,
            content=content,
            status=MessageStatus.QUEUED,
        )
        self.session.add(message)
        await self.session.flush()
        if contact.opted_out:
            message.status = MessageStatus.FAILED
            message.error_detail = "Contact opted out"
            return message
        try:
            result = await send(contact.phone_number)
        except RealDeliveryBlockedError as exc:
            message.status = MessageStatus.FAILED
            message.error_detail = str(exc)
            return message
        message.status = result.status
        message.error_detail = result.error
        if result.provider_message_id:
            message.provider_message_id = result.provider_message_id
        if result.status == MessageStatus.SENT:
            message.sent_at = datetime.now(UTC)
        conversation.last_message_at = datetime.now(UTC)
        return message

    async def send_template(
        self,
        conversation: Conversation,
        template_name: str,
        language_code: str,
        components: list[dict],
        *,
        sender_type: SenderType,
        sender_user_id: uuid.UUID | None = None,
    ) -> Message:
        if self.messaging is None or not hasattr(self.messaging, "send_template"):
            raise AppError(
                "Template message hanya tersedia pada WhatsApp Cloud API.",
                code="TEMPLATE_PROVIDER_UNAVAILABLE",
            )
        send_template = self.messaging.send_template  # type: ignore[attr-defined]

        async def send(to_phone: str) -> SendResult:
            return await send_template(to_phone, template_name, language_code, components)

        return await self._send_special(
            conversation,
            message_type="template",
            content=f"[WhatsApp template: {template_name}]",
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            send=send,
        )

    async def send_media(
        self,
        conversation: Conversation,
        media_type: str,
        media_id: str,
        caption: str | None,
        filename: str | None,
        *,
        sender_type: SenderType,
        sender_user_id: uuid.UUID | None = None,
    ) -> Message:
        if self.messaging is None or not hasattr(self.messaging, "send_media"):
            raise AppError(
                "Media message hanya tersedia pada WhatsApp Cloud API.",
                code="MEDIA_PROVIDER_UNAVAILABLE",
            )
        if getattr(self.messaging, "name", None) == ProviderName.WHATSAPP_CLOUD:
            last_inbound = conversation.last_inbound_at
            if (
                last_inbound is None
                or datetime.now(UTC) - last_inbound > timedelta(hours=24)
            ):
                raise AppError(
                    "Jendela layanan 24 jam telah berakhir. Gunakan template WhatsApp.",
                    code="WHATSAPP_TEMPLATE_REQUIRED",
                )
        send_media = self.messaging.send_media  # type: ignore[attr-defined]

        async def send(to_phone: str) -> SendResult:
            return await send_media(to_phone, media_type, media_id, caption, filename)

        return await self._send_special(
            conversation,
            message_type=media_type,
            content=caption or f"[{media_type}]",
            sender_type=sender_type,
            sender_user_id=sender_user_id,
            send=send,
        )

    async def apply_status_update(self, update: StatusUpdate) -> Message | None:
        """Apply sent/delivered/read/failed from the provider. Status never moves backwards."""
        message = await self.session.scalar(
            select(Message).where(Message.provider_message_id == update.provider_message_id)
        )
        if message is None or message.direction != MessageDirection.OUTBOUND:
            return None

        try:
            new_status = MessageStatus(update.status)
        except ValueError:
            logger.info("Unknown message status ignored: %s", update.status)
            return message

        if new_status == MessageStatus.FAILED:
            message.status = MessageStatus.FAILED
            message.error_detail = update.error or message.error_detail
            return message

        current_rank = OUTBOUND_STATUS_RANK.get(MessageStatus(message.status), -1)
        new_rank = OUTBOUND_STATUS_RANK.get(new_status, -1)
        if new_rank <= current_rank:
            return message

        message.status = new_status
        if new_status == MessageStatus.SENT:
            message.sent_at = message.sent_at or update.timestamp
        if new_status in (MessageStatus.DELIVERED, MessageStatus.READ):
            message.delivered_at = message.delivered_at or update.timestamp
        if new_status == MessageStatus.READ:
            message.read_at = update.timestamp
        return message

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        result = await self.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result)

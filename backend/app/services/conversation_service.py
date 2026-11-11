import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Contact, Conversation, Lead
from app.models.enums import ConversationHandler, ConversationStatus


class ConversationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Percakapan tidak ditemukan", code="CONVERSATION_NOT_FOUND")
        return conversation

    async def get_open_for_contact(self, contact_id: uuid.UUID) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation)
            .where(
                Conversation.contact_id == contact_id,
                Conversation.status == ConversationStatus.OPEN,
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )

    async def get_or_create_open(
        self, contact: Contact, *, provider: str, lead: Lead | None = None
    ) -> tuple[Conversation, bool]:
        conversation = await self.get_open_for_contact(contact.id)
        if conversation:
            if lead and conversation.lead_id is None:
                conversation.lead_id = lead.id
            return conversation, False
        return await self._create(contact, provider=provider, lead=lead), True

    async def start_new(
        self, contact: Contact, *, provider: str, lead: Lead | None = None
    ) -> Conversation:
        """Close any open conversation and start a fresh one."""
        await self.session.execute(
            update(Conversation)
            .where(
                Conversation.contact_id == contact.id,
                Conversation.status == ConversationStatus.OPEN,
            )
            .values(status=ConversationStatus.CLOSED, closed_at=datetime.now(UTC))
        )
        return await self._create(contact, provider=provider, lead=lead)

    async def _create(self, contact: Contact, *, provider: str, lead: Lead | None) -> Conversation:
        conversation = Conversation(
            contact_id=contact.id,
            lead_id=lead.id if lead else None,
            provider=provider,
            status=ConversationStatus.OPEN,
            handler=ConversationHandler.AI,
            unread_count=0,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

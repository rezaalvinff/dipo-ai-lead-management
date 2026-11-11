"""ONE entry point for every incoming customer message.

The simulator and the WhatsApp Cloud webhook both call InboundMessageService.handle().
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.whatsapp.base import InboundMessage
from app.core.config import Settings
from app.core.phone import mask_phone
from app.models import Contact, Conversation, Lead, Message
from app.models.enums import (
    ActorType,
    ConversationHandler,
    ConversationStatus,
    LeadSource,
    ProviderName,
)
from app.services.audit_service import record_audit
from app.services.contact_service import ContactService
from app.services.conversation_service import ConversationService
from app.services.lead_service import LeadService
from app.services.message_service import MessageService
from app.workers.queue import JobQueue

logger = logging.getLogger(__name__)


@dataclass
class InboundResult:
    contact: Contact
    conversation: Conversation
    lead: Lead
    message: Message | None  # None when the message was a duplicate
    ai_reply_queued: bool

    @property
    def duplicate(self) -> bool:
        return self.message is None


class InboundMessageService:
    def __init__(self, session: AsyncSession, settings: Settings, queue: JobQueue):
        self.session = session
        self.settings = settings
        self.queue = queue

    async def handle(self, inbound: InboundMessage) -> InboundResult:
        is_simulator = inbound.provider == ProviderName.SIMULATED
        # Outside production every contact is treated as test data.
        is_simulated = is_simulator or not self.settings.is_production

        contact = await ContactService(self.session).get_or_create(
            inbound.from_phone,
            display_name=inbound.profile_name,
            wa_id=inbound.wa_id,
            is_simulated=is_simulated,
        )
        lead, lead_created = await LeadService(self.session).get_or_create_active(
            contact,
            source=LeadSource.SIMULATOR if is_simulator else LeadSource.WHATSAPP,
            referral=inbound.referral,
        )
        conversation, _ = await ConversationService(self.session).get_or_create_open(
            contact, provider=inbound.provider, lead=lead
        )
        message = await MessageService(self.session).record_inbound(conversation, inbound)

        if message is None:
            await self.session.commit()
            return InboundResult(contact, conversation, lead, None, ai_reply_queued=False)

        if lead_created:
            record_audit(
                self.session,
                action="lead.created",
                entity_type="lead",
                entity_id=lead.id,
                actor_type=ActorType.CONTACT,
                data={"source": lead.source},
            )
        await self.session.commit()
        logger.info(
            "Inbound stored provider=%s from=%s conversation=%s",
            inbound.provider,
            mask_phone(inbound.from_phone),
            conversation.id,
        )

        should_reply = (
            conversation.handler == ConversationHandler.AI
            and conversation.status == ConversationStatus.OPEN
        )
        if should_reply:
            await self.queue.enqueue_ai_reply(message.id)
        return InboundResult(contact, conversation, lead, message, ai_reply_queued=should_reply)

"""Process WhatsApp Cloud API webhooks: duplicate protection + routing to shared services."""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.whatsapp.cloud import parse_webhook
from app.core.config import Settings
from app.models import WebhookEvent
from app.models.enums import ProviderName
from app.services.inbound_service import InboundMessageService
from app.services.message_service import MessageService
from app.workers.queue import JobQueue

logger = logging.getLogger(__name__)


@dataclass
class WebhookResult:
    duplicate: bool = False
    messages_stored: int = 0
    messages_duplicate: int = 0
    statuses_applied: int = 0
    errors: list[str] = field(default_factory=list)


class WhatsAppWebhookService:
    def __init__(self, session: AsyncSession, settings: Settings, queue: JobQueue):
        self.session = session
        self.settings = settings
        self.queue = queue

    async def process(self, raw_body: bytes, payload: dict) -> WebhookResult:
        event_key = hashlib.sha256(raw_body).hexdigest()

        # Layer 1 of duplicate protection: the exact same delivery is processed once.
        inserted = await self.session.scalar(
            insert(WebhookEvent)
            .values(source=ProviderName.WHATSAPP_CLOUD, event_key=event_key, payload=payload)
            .on_conflict_do_nothing(index_elements=[WebhookEvent.event_key])
            .returning(WebhookEvent.id)
        )
        await self.session.commit()
        if inserted is None:
            logger.info("Duplicate webhook delivery ignored")
            return WebhookResult(duplicate=True)

        result = WebhookResult()
        try:
            inbound_messages, statuses = parse_webhook(payload)
            inbound_service = InboundMessageService(self.session, self.settings, self.queue)
            for inbound in inbound_messages:
                # Layer 2: unique provider_message_id (wamid) inside MessageService.
                outcome = await inbound_service.handle(inbound)
                if outcome.duplicate:
                    result.messages_duplicate += 1
                else:
                    result.messages_stored += 1

            message_service = MessageService(self.session)
            for status_update in statuses:
                if await message_service.apply_status_update(status_update):
                    result.statuses_applied += 1
            await self.session.execute(
                update(WebhookEvent)
                .where(WebhookEvent.id == inserted)
                .values(processed_at=datetime.now(UTC))
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            # Forget this delivery so Meta's retry can be processed again.
            await self.session.execute(delete(WebhookEvent).where(WebhookEvent.id == inserted))
            await self.session.commit()
            raise
        return result

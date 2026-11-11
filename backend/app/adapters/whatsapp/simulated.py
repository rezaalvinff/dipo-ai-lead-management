"""Simulated WhatsApp: never contacts any external system.

Outgoing messages are only given a fake ID; the services store them in the
database exactly like real ones, and the simulator UI reads them from there.
"""

import logging
import uuid

from app.adapters.whatsapp.base import SendResult
from app.core.phone import mask_phone
from app.models.enums import MessageStatus, ProviderName

logger = logging.getLogger(__name__)


def new_simulated_message_id(prefix: str = "sim") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class SimulatedWhatsAppAdapter:
    name = ProviderName.SIMULATED

    async def send_text(self, to_phone: str, text: str) -> SendResult:
        message_id = new_simulated_message_id("sim-out")
        logger.info("[SIMULATED] send_text to=%s chars=%d", mask_phone(to_phone), len(text))
        return SendResult(provider_message_id=message_id, status=MessageStatus.SENT)

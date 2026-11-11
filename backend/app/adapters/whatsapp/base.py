"""Provider-neutral message types and the MessagingProvider interface.

Business logic (services) only knows these types. Each adapter converts its own
format (simulator request, Meta webhook JSON) into them.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class InboundMessage:
    provider: str
    from_phone: str  # E.164
    provider_message_id: str
    text: str
    timestamp: datetime
    message_type: str = "text"
    profile_name: str | None = None
    wa_id: str | None = None
    referral: dict | None = None  # Click-to-WhatsApp ad data, if any
    raw: dict | None = None


@dataclass(frozen=True)
class StatusUpdate:
    provider_message_id: str
    status: str  # sent | delivered | read | failed
    timestamp: datetime
    error: str | None = None


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str
    status: str  # sent | failed
    error: str | None = None
    raw: dict = field(default_factory=dict)


class MessagingProvider(Protocol):
    name: str

    async def send_text(self, to_phone: str, text: str) -> SendResult: ...

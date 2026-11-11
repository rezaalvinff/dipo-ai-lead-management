"""Allowed values for string columns. Stored as varchar, validated in the app."""

from enum import StrEnum


class RoleName(StrEnum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    SALES = "sales"


class ProviderName(StrEnum):
    SIMULATED = "simulated"
    WHATSAPP_CLOUD = "whatsapp_cloud"


class ConversationHandler(StrEnum):
    AI = "ai"
    ADMIN_QUEUE = "admin_queue"
    SALES = "sales"


class ConversationStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SenderType(StrEnum):
    CONTACT = "contact"
    AI = "ai"
    SALES = "sales"
    ADMIN = "admin"
    SYSTEM = "system"


class MessageStatus(StrEnum):
    RECEIVED = "received"  # inbound
    QUEUED = "queued"  # outbound, before provider accepted it
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# Outbound status can only move forward (a late "delivered" must not undo "read").
OUTBOUND_STATUS_RANK = {
    MessageStatus.QUEUED: 0,
    MessageStatus.SENT: 1,
    MessageStatus.DELIVERED: 2,
    MessageStatus.READ: 3,
}


class LeadTemperature(StrEnum):
    COLD = "cold"
    WARM = "warm"


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    ASSIGNED = "assigned"
    CONTACTED = "contacted"
    WON = "won"
    LOST = "lost"


class LeadSource(StrEnum):
    WHATSAPP = "whatsapp"
    SIMULATOR = "simulator"
    CTWA_AD = "ctwa_ad"


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    AI = "ai"
    CONTACT = "contact"

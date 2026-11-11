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
    AI = "ai"  # the AI agent replies automatically
    ADMIN_QUEUE = "admin_queue"  # waiting for a human (AI stays silent)
    SALES = "sales"  # a sales person took over (AI stays silent)
    ADMIN = "admin"  # an admin/supervisor took over (AI stays silent)


HUMAN_HANDLERS = (ConversationHandler.SALES, ConversationHandler.ADMIN)


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


class KnowledgeStatus(StrEnum):
    DRAFT = "draft"  # not visible to the AI
    APPROVED = "approved"  # the AI may use it
    ARCHIVED = "archived"  # hidden, kept for history


class KnowledgeCategory(StrEnum):
    SPEC = "spec"
    PRICE = "price"
    PROMO = "promo"
    DP = "dp"
    INSTALLMENT = "installment"
    FAQ = "faq"
    DEALER = "dealer"
    POLICY = "policy"


class QualificationField(StrEnum):
    NAME = "name"
    DOMICILE = "domicile"
    VEHICLE = "vehicle"


QUALIFICATION_ORDER = (
    QualificationField.NAME,
    QualificationField.DOMICILE,
    QualificationField.VEHICLE,
)


class FieldStatus(StrEnum):
    MISSING = "missing"
    COLLECTED = "collected"
    DECLINED = "declined"  # customer refused or did not answer after max asks


class QualificationStage(StrEnum):
    COLLECTING = "collecting"
    HANDED_OVER = "handed_over"


class HandoverReason(StrEnum):
    QUALIFICATION_COMPLETE = "qualification_complete"
    PARTIAL_DATA = "partial_data"  # some fields declined/unanswered
    HUMAN_REQUESTED = "human_requested"
    AI_UNAVAILABLE = "ai_unavailable"
    AI_DISABLED = "ai_disabled"
    RETURNING_CUSTOMER = "returning_customer"
    MANUAL_TAKEOVER = "manual_takeover"

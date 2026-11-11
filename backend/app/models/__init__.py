"""Import every model here so Alembic sees the full metadata."""

from app.models.ai_interaction import AIInteraction
from app.models.base import Base
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.knowledge import KnowledgeBaseArticle, VehicleModel, VehicleVariant
from app.models.lead import Assignment, Lead
from app.models.qualification import QualificationState
from app.models.settings import AppSetting
from app.models.territory import Territory, TerritoryMapping
from app.models.tracking import AuditLog, ConversionEvent, WebhookEvent
from app.models.user import AgentProfile, Role, User

__all__ = [
    "AIInteraction",
    "AppSetting",
    "QualificationState",
    "VehicleModel",
    "VehicleVariant",
    "AgentProfile",
    "Assignment",
    "AuditLog",
    "Base",
    "Campaign",
    "Contact",
    "Conversation",
    "ConversionEvent",
    "KnowledgeBaseArticle",
    "Lead",
    "Message",
    "Role",
    "Territory",
    "TerritoryMapping",
    "User",
    "WebhookEvent",
]

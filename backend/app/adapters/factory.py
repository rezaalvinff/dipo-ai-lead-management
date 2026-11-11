"""Choose adapters once, from configuration."""

from app.adapters.ai.base import AIProvider
from app.adapters.ai.mock import MockAIProvider
from app.adapters.whatsapp.base import MessagingProvider
from app.adapters.whatsapp.cloud import WhatsAppCloudAdapter
from app.adapters.whatsapp.simulated import SimulatedWhatsAppAdapter
from app.core.config import Settings, WhatsAppProviderName


def build_messaging_provider(settings: Settings) -> MessagingProvider:
    if settings.whatsapp_provider == WhatsAppProviderName.WHATSAPP_CLOUD:
        return WhatsAppCloudAdapter(settings)
    return SimulatedWhatsAppAdapter()


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "mock":
        return MockAIProvider()
    raise ValueError(
        f"AI_PROVIDER '{settings.ai_provider}' is not implemented yet. Use 'mock' for now."
    )

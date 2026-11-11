"""Choose adapters once, from configuration."""

from app.adapters.ai.base import AIProvider
from app.adapters.ai.mock import MockAIProvider
from app.adapters.whatsapp.base import MessagingProvider
from app.adapters.whatsapp.cloud import WhatsAppCloudAdapter
from app.adapters.whatsapp.simulated import SimulatedWhatsAppAdapter
from app.core.config import AIProviderName, Settings, WhatsAppProviderName


def build_messaging_provider(settings: Settings) -> MessagingProvider:
    if settings.whatsapp_provider == WhatsAppProviderName.WHATSAPP_CLOUD:
        return WhatsAppCloudAdapter(settings)
    return SimulatedWhatsAppAdapter()


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == AIProviderName.ANTHROPIC:
        from app.adapters.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)
    if settings.ai_provider == AIProviderName.OPENAI:
        from app.adapters.ai.openai_provider import OpenAIProvider

        return OpenAIProvider(settings)
    return MockAIProvider()

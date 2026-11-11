"""SECOND safety layer of Development Mode.

Every adapter that talks to a real external system (WhatsApp Cloud API,
Meta Conversions API) must call ``ensure_real_delivery_allowed`` right before
sending anything. This protects us even if the startup validation were
bypassed (e.g. a test or a script that builds an adapter manually).
"""

from app.core.config import Settings


class RealDeliveryBlockedError(RuntimeError):
    """Raised when something tries to reach a real external system when not allowed."""


def ensure_real_delivery_allowed(settings: Settings, action: str) -> None:
    if not settings.is_production:
        raise RealDeliveryBlockedError(
            f"Blocked '{action}': real delivery is only allowed when APP_ENV=production "
            f"(current APP_ENV={settings.app_env})."
        )
    if not settings.whatsapp_cloud_send_enabled:
        raise RealDeliveryBlockedError(f"Blocked '{action}': WHATSAPP_CLOUD_SEND_ENABLED is false.")

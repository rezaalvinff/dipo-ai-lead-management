from fastapi import APIRouter, Depends

from app.api.deps import get_ctx, require_roles
from app.core.context import AppContext
from app.models import User
from app.models.enums import RoleName

router = APIRouter(prefix="/integrations/whatsapp", tags=["WhatsApp integration"])


@router.get("/status")
async def whatsapp_status(
    _: User = Depends(require_roles(RoleName.ADMIN, RoleName.SUPERVISOR)),
    ctx: AppContext = Depends(get_ctx),
):
    settings = ctx.settings
    configured = {
        "access_token": bool(settings.whatsapp_access_token),
        "phone_number_id": bool(settings.whatsapp_phone_number_id),
        "app_secret": bool(settings.whatsapp_app_secret),
        "webhook_verify_token": bool(settings.whatsapp_webhook_verify_token),
    }
    ready = all(configured.values())
    return {
        "app_env": settings.app_env,
        "provider": settings.whatsapp_provider,
        "api_version": settings.whatsapp_api_version,
        "simulator_enabled": settings.simulator_enabled,
        "send_enabled": settings.whatsapp_cloud_send_enabled,
        "credentials_configured": configured,
        "credentials_complete": ready,
        "webhook_path": "/api/v1/webhooks/whatsapp",
        "webhook_verification_supported": True,
        "incoming_text_supported": True,
        "outgoing_text_supported": True,
        "templates_supported": False,
        "media_supported": False,
        "production_activation_ready": bool(
            settings.is_production
            and settings.whatsapp_provider == "whatsapp_cloud"
            and ready
            and settings.whatsapp_cloud_send_enabled
            and not settings.simulator_enabled
        ),
        "note": (
            "Tidak ada token atau secret yang ditampilkan. Pengiriman sungguhan "
            "tetap nonaktif sampai aktivasi eksplisit."
        ),
    }

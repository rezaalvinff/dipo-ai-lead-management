"""Meta WhatsApp Cloud API webhook endpoints.

GET  /webhooks/whatsapp  -> verification handshake (hub.challenge)
POST /webhooks/whatsapp  -> incoming messages + message statuses
"""

import hmac
import json
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.whatsapp.cloud import SIGNATURE_HEADER, verify_signature
from app.api.deps import get_ctx, get_session
from app.core.context import AppContext
from app.core.errors import AppError, ForbiddenError
from app.services.webhook_service import WhatsAppWebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.get("/whatsapp", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
    ctx: AppContext = Depends(get_ctx),
) -> PlainTextResponse:
    expected = ctx.settings.whatsapp_webhook_verify_token
    if (
        hub_mode == "subscribe"
        and expected
        and hmac.compare_digest(hub_verify_token.encode(), expected.encode())
    ):
        return PlainTextResponse(hub_challenge)
    raise ForbiddenError("Verifikasi webhook gagal", code="WEBHOOK_VERIFY_FAILED")


@router.post("/whatsapp")
async def receive_webhook(
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    raw_body = await request.body()
    if not verify_signature(
        ctx.settings.whatsapp_app_secret, raw_body, request.headers.get(SIGNATURE_HEADER)
    ):
        logger.warning("Rejected webhook with invalid signature")
        raise ForbiddenError("Signature webhook tidak valid", code="INVALID_SIGNATURE")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise AppError("Body webhook bukan JSON", code="INVALID_JSON") from exc
    if payload.get("object") != "whatsapp_business_account":
        return JSONResponse({"status": "ignored"})

    result = await WhatsAppWebhookService(session, ctx.settings, ctx.queue).process(
        raw_body, payload
    )
    return JSONResponse(
        {
            "status": "duplicate" if result.duplicate else "ok",
            "messages_stored": result.messages_stored,
            "messages_duplicate": result.messages_duplicate,
            "statuses_applied": result.statuses_applied,
        }
    )

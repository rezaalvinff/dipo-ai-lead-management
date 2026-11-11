"""Meta WhatsApp Cloud API adapter (FOUNDATION ONLY — not activated yet).

Sending is blocked unless APP_ENV=production AND WHATSAPP_CLOUD_SEND_ENABLED=true
(see app.core.safety). Parsing and signature validation are pure functions so
they can be tested with dummy payloads without any real number.
"""

import hashlib
import hmac
import logging
from datetime import UTC, datetime

import httpx

from app.adapters.whatsapp.base import InboundMessage, SendResult, StatusUpdate
from app.core.config import Settings
from app.core.phone import mask_phone, normalize_phone
from app.core.safety import ensure_real_delivery_allowed
from app.models.enums import MessageStatus, ProviderName

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Hub-Signature-256"


def verify_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    """Validate Meta's X-Hub-Signature-256 header ("sha256=<hex hmac>")."""
    if not app_secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def _ts(value: str | None) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _message_text(msg: dict) -> str:
    msg_type = msg.get("type")
    if msg_type == "text":
        return msg.get("text", {}).get("body", "")
    if msg_type == "button":
        return msg.get("button", {}).get("text", "")
    if msg_type == "interactive":
        interactive = msg.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return reply.get("title", "")
    if msg_type in {"image", "video", "document", "audio", "sticker"}:
        return msg.get(msg_type, {}).get("caption", "") or f"[{msg_type}]"
    if msg_type == "location":
        return "[location]"
    return f"[{msg_type}]"


def parse_webhook(payload: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    """Convert a Meta webhook payload into provider-neutral objects."""
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value", {}) or {}
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts", []) or []
            }
            for msg in value.get("messages", []) or []:
                wa_id = msg.get("from")
                if not wa_id or not msg.get("id"):
                    continue
                messages.append(
                    InboundMessage(
                        provider=ProviderName.WHATSAPP_CLOUD,
                        from_phone=normalize_phone(wa_id),
                        wa_id=wa_id,
                        profile_name=names.get(wa_id),
                        provider_message_id=msg["id"],
                        message_type=msg.get("type", "text"),
                        text=_message_text(msg),
                        timestamp=_ts(msg.get("timestamp")),
                        referral=msg.get("referral"),
                        raw=msg,
                    )
                )
            for st in value.get("statuses", []) or []:
                if not st.get("id") or not st.get("status"):
                    continue
                errors = st.get("errors") or []
                statuses.append(
                    StatusUpdate(
                        provider_message_id=st["id"],
                        status=st["status"],
                        timestamp=_ts(st.get("timestamp")),
                        error=(errors[0].get("title") if errors else None),
                    )
                )
    return messages, statuses


class WhatsAppCloudAdapter:
    name = ProviderName.WHATSAPP_CLOUD

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http_client

    def _url(self) -> str:
        s = self._settings
        base = f"{s.whatsapp_api_base_url}/{s.whatsapp_api_version}"
        return f"{base}/{s.whatsapp_phone_number_id}/messages"

    async def _send_payload(self, to_phone: str, body: dict, operation: str) -> SendResult:
        ensure_real_delivery_allowed(self._settings, operation)
        headers = {"Authorization": f"Bearer {self._settings.whatsapp_access_token}"}
        client = self._http or httpx.AsyncClient(timeout=15)
        try:
            response = await client.post(self._url(), json=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("WhatsApp send failed to=%s: %s", mask_phone(to_phone), exc)
            return SendResult(provider_message_id="", status=MessageStatus.FAILED, error=str(exc))
        finally:
            if self._http is None:
                await client.aclose()

        data = response.json() if response.content else {}
        if response.status_code >= 400:
            error = (data.get("error") or {}).get("message", f"HTTP {response.status_code}")
            return SendResult(
                provider_message_id="", status=MessageStatus.FAILED, error=error, raw=data
            )
        wamid = (data.get("messages") or [{}])[0].get("id", "")
        return SendResult(provider_message_id=wamid, status=MessageStatus.SENT, raw=data)

    async def send_text(self, to_phone: str, text: str) -> SendResult:
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return await self._send_payload(to_phone, body, "whatsapp_cloud.send_text")

    async def send_template(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "id",
        components: list[dict] | None = None,
    ) -> SendResult:
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.lstrip("+"),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components or [],
            },
        }
        return await self._send_payload(to_phone, body, "whatsapp_cloud.send_template")

    async def send_media(
        self,
        to_phone: str,
        media_type: str,
        media_id: str,
        caption: str | None = None,
        filename: str | None = None,
    ) -> SendResult:
        if media_type not in {"image", "video", "document", "audio"}:
            return SendResult(
                provider_message_id="",
                status=MessageStatus.FAILED,
                error="Unsupported WhatsApp media type",
            )
        media: dict = {"id": media_id}
        if caption and media_type in {"image", "video", "document"}:
            media["caption"] = caption
        if filename and media_type == "document":
            media["filename"] = filename
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.lstrip("+"),
            "type": media_type,
            media_type: media,
        }
        return await self._send_payload(to_phone, body, "whatsapp_cloud.send_media")

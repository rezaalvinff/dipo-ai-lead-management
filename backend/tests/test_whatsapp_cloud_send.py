import json

import httpx
import pytest

from app.adapters.whatsapp.cloud import WhatsAppCloudAdapter
from app.core.config import AppEnv, Settings, WhatsAppProviderName


def _production_settings():
    return Settings(
        _env_file=None,
        app_env=AppEnv.PRODUCTION,
        simulator_enabled=False,
        whatsapp_provider=WhatsAppProviderName.WHATSAPP_CLOUD,
        whatsapp_cloud_send_enabled=True,
        whatsapp_access_token="dummy-meta-token-for-tests",
        whatsapp_phone_number_id="123456789",
        whatsapp_app_secret="dummy-meta-app-secret",
        whatsapp_webhook_verify_token="dummy-verify-token",
        jwt_secret="x9Kq2LmZ7vRt4WbN8cYp3HsJ6dFg1QaE",
    )


@pytest.mark.asyncio
async def test_template_message_uses_meta_template_payload():
    captured = {}

    async def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.template.test"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = WhatsAppCloudAdapter(_production_settings(), client)
        result = await adapter.send_template(
            "+6281234567890",
            "dipo_follow_up",
            "id",
            [{"type": "body", "parameters": [{"type": "text", "text": "Andi"}]}],
        )

    assert result.provider_message_id == "wamid.template.test"
    assert captured["body"]["type"] == "template"
    assert captured["body"]["template"]["name"] == "dipo_follow_up"
    assert captured["body"]["template"]["language"] == {"code": "id"}


@pytest.mark.asyncio
async def test_media_message_uses_existing_meta_media_id():
    captured = {}

    async def handler(request: httpx.Request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.media.test"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = WhatsAppCloudAdapter(_production_settings(), client)
        result = await adapter.send_media(
            "+6281234567890", "image", "MEDIA_ID_DUMMY", "Brosur DIPO", None
        )

    assert result.provider_message_id == "wamid.media.test"
    assert captured["body"]["type"] == "image"
    assert captured["body"]["image"] == {
        "id": "MEDIA_ID_DUMMY",
        "caption": "Brosur DIPO",
    }

"""WhatsApp Cloud webhook tests with DUMMY payloads (no real number involved)."""

import hashlib
import hmac
import json

from sqlalchemy import select

from app.models import Contact, Conversation, Lead, Message
from tests.conftest import TEST_APP_SECRET, TEST_VERIFY_TOKEN

URL = "/api/v1/webhooks/whatsapp"
DUMMY_WA_ID = "6280000000555"


def _signed(payload: dict, secret: str = TEST_APP_SECRET) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": signature, "Content-Type": "application/json"}


def _value(**value) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "0", "changes": [{"field": "messages", "value": value}]}],
    }


def text_payload(wamid: str, text: str, referral: dict | None = None) -> dict:
    msg = {
        "from": DUMMY_WA_ID,
        "id": wamid,
        "timestamp": "1767225600",
        "type": "text",
        "text": {"body": text},
    }
    if referral:
        msg["referral"] = referral
    return _value(
        messaging_product="whatsapp",
        contacts=[{"wa_id": DUMMY_WA_ID, "profile": {"name": "Customer Webhook Dummy"}}],
        messages=[msg],
    )


async def test_verification_handshake(client):
    ok = await client.get(
        URL,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": TEST_VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )
    assert ok.status_code == 200 and ok.text == "12345"

    bad = await client.get(
        URL, params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"}
    )
    assert bad.status_code == 403


async def test_invalid_signature_rejected(client):
    body, headers = _signed(text_payload("wamid.A", "Halo"), secret="wrong-secret")
    response = await client.post(URL, content=body, headers=headers)
    assert response.status_code == 403
    unsigned = await client.post(URL, content=body)
    assert unsigned.status_code == 403


async def test_incoming_message_uses_shared_services(client, app):
    body, headers = _signed(text_payload("wamid.IN-1", "Halo dari webhook"))
    response = await client.post(URL, content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["messages_stored"] == 1

    async with app.state.ctx.session_factory() as session:
        contact = await session.scalar(select(Contact))
        assert contact.phone_number == "+" + DUMMY_WA_ID
        assert contact.display_name == "Customer Webhook Dummy"
        assert contact.is_simulated  # development: treated as test data
        conversation = await session.scalar(select(Conversation))
        assert conversation.provider == "whatsapp_cloud"
        messages = list(await session.scalars(select(Message).order_by(Message.created_at)))
        assert [m.direction for m in messages] == ["inbound", "outbound"]
        # In development the reply goes out through the SIMULATED adapter, never Meta.
        assert messages[1].provider == "simulated"
        assert messages[1].provider_message_id.startswith("sim-out-")


async def test_duplicate_webhook_protection(client, app):
    body, headers = _signed(text_payload("wamid.DUP-1", "Halo"))
    first = await client.post(URL, content=body, headers=headers)
    again = await client.post(URL, content=body, headers=headers)
    assert first.json()["status"] == "ok"
    assert again.json()["status"] == "duplicate"

    # Different delivery body, same wamid -> message-level protection.
    payload = text_payload("wamid.DUP-1", "Halo")
    payload["entry"][0]["id"] = "retry"
    body2, headers2 = _signed(payload)
    third = await client.post(URL, content=body2, headers=headers2)
    assert third.json()["messages_duplicate"] == 1

    async with app.state.ctx.session_factory() as session:
        inbound = list(await session.scalars(select(Message).where(Message.direction == "inbound")))
        assert len(inbound) == 1


async def test_status_updates_applied(client, app):
    body, headers = _signed(text_payload("wamid.IN-2", "Halo"))
    await client.post(URL, content=body, headers=headers)
    async with app.state.ctx.session_factory() as session:
        outbound = await session.scalar(select(Message).where(Message.direction == "outbound"))
        out_id = outbound.provider_message_id

    for status in ("delivered", "read"):
        payload = _value(statuses=[{"id": out_id, "status": status, "timestamp": "1767225700"}])
        body, headers = _signed(payload)
        response = await client.post(URL, content=body, headers=headers)
        assert response.json()["statuses_applied"] == 1

    failed = _value(
        statuses=[
            {
                "id": out_id,
                "status": "failed",
                "timestamp": "1767225800",
                "errors": [{"code": 131047, "title": "Re-engagement message"}],
            }
        ]
    )
    body, headers = _signed(failed)
    await client.post(URL, content=body, headers=headers)

    async with app.state.ctx.session_factory() as session:
        msg = await session.scalar(select(Message).where(Message.provider_message_id == out_id))
        assert msg.status == "failed"
        assert msg.error_detail == "Re-engagement message"
        assert msg.read_at is not None


async def test_ad_referral_marks_lead_source(client, app):
    referral = {"source_type": "ad", "source_id": "000111", "headline": "Promo Dummy"}
    body, headers = _signed(text_payload("wamid.AD-1", "Info promo", referral=referral))
    await client.post(URL, content=body, headers=headers)
    async with app.state.ctx.session_factory() as session:
        lead = await session.scalar(select(Lead))
        assert lead.source == "ctwa_ad"
        assert lead.ad_referral["source_id"] == "000111"


async def test_non_whatsapp_object_ignored(client):
    body, headers = _signed({"object": "page", "entry": []})
    response = await client.post(URL, content=body, headers=headers)
    assert response.json() == {"status": "ignored"}

import hashlib
import hmac

import pytest

from app.adapters.whatsapp.cloud import parse_webhook, verify_signature
from app.core.phone import mask_phone, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0812-3456-7890", "+6281234567890"),
        ("6281234567890", "+6281234567890"),
        ("+62 812 3456 7890", "+6281234567890"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_phone_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_phone("abc")


def test_mask_phone_hides_middle():
    assert mask_phone("+6280000000123") == "+6280******123"


def test_signature_validation():
    body = b'{"hello":"world"}'
    good = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_signature("secret", body, good)
    assert not verify_signature("secret", body, "sha256=deadbeef")
    assert not verify_signature("secret", body, None)
    assert not verify_signature("", body, good)  # no secret configured -> reject


def test_parse_webhook_messages_and_statuses():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "contacts": [{"wa_id": "6280000000777", "profile": {"name": "Dummy"}}],
                            "messages": [
                                {
                                    "from": "6280000000777",
                                    "id": "wamid.IN1",
                                    "timestamp": "1767225600",
                                    "type": "text",
                                    "text": {"body": "Halo"},
                                }
                            ],
                            "statuses": [
                                {"id": "wamid.OUT1", "status": "read", "timestamp": "1767225601"}
                            ],
                        },
                    }
                ]
            }
        ],
    }
    messages, statuses = parse_webhook(payload)
    assert len(messages) == 1
    assert messages[0].from_phone == "+6280000000777"
    assert messages[0].profile_name == "Dummy"
    assert messages[0].text == "Halo"
    assert statuses[0].provider_message_id == "wamid.OUT1"
    assert statuses[0].status == "read"

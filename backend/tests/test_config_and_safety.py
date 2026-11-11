import httpx
import pytest

from app.adapters.whatsapp.cloud import WhatsAppCloudAdapter
from app.core.config import ConfigurationError
from app.core.safety import RealDeliveryBlockedError, ensure_real_delivery_allowed
from tests.conftest import STRONG_SECRET, make_settings

PROD_BASE = {
    "app_env": "production",
    "simulator_enabled": False,
    "jwt_secret": STRONG_SECRET,
}
CLOUD_CREDS = {
    "whatsapp_provider": "whatsapp_cloud",
    "whatsapp_access_token": "dummy-token",
    "whatsapp_phone_number_id": "000000000000000",
    "whatsapp_app_secret": "dummy-secret",
    "whatsapp_webhook_verify_token": "dummy-verify",
}


def test_development_defaults_are_safe():
    s = make_settings()
    assert s.app_env == "development"
    assert s.whatsapp_provider == "simulated"
    assert s.conversion_provider == "noop"


@pytest.mark.parametrize(
    "overrides",
    [
        {"whatsapp_provider": "whatsapp_cloud"},
        {"conversion_provider": "meta_capi"},
        {"whatsapp_cloud_send_enabled": True},
    ],
)
def test_development_refuses_real_providers(overrides):
    with pytest.raises(ConfigurationError):
        make_settings(**overrides)


def test_production_refuses_simulator():
    with pytest.raises(ConfigurationError, match="SIMULATOR_ENABLED"):
        make_settings(**{**PROD_BASE, "simulator_enabled": True})


def test_production_refuses_weak_jwt_secret():
    with pytest.raises(ConfigurationError, match="JWT_SECRET"):
        make_settings(**{**PROD_BASE, "jwt_secret": "changeme"})


def test_production_cloud_requires_credentials():
    with pytest.raises(ConfigurationError, match="WHATSAPP_ACCESS_TOKEN"):
        make_settings(**PROD_BASE, whatsapp_provider="whatsapp_cloud", whatsapp_access_token="")


def test_valid_production_config_is_accepted():
    s = make_settings(**PROD_BASE, **CLOUD_CREDS)
    assert s.is_production


def test_guard_blocks_development():
    with pytest.raises(RealDeliveryBlockedError):
        ensure_real_delivery_allowed(make_settings(), "test")


def test_guard_blocks_production_without_kill_switch():
    s = make_settings(**PROD_BASE, **CLOUD_CREDS)
    with pytest.raises(RealDeliveryBlockedError, match="WHATSAPP_CLOUD_SEND_ENABLED"):
        ensure_real_delivery_allowed(s, "test")


class RecordingTransport(httpx.MockTransport):
    """Fake HTTP layer: records requests, never touches the internet."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.DUMMY123"}]})


async def test_cloud_adapter_never_sends_in_development():
    transport = RecordingTransport()
    adapter = WhatsAppCloudAdapter(make_settings(), httpx.AsyncClient(transport=transport))
    with pytest.raises(RealDeliveryBlockedError):
        await adapter.send_text("+6280000000001", "halo")
    assert transport.requests == []


async def test_cloud_adapter_request_shape_when_fully_enabled():
    """Only with production + kill switch on; still uses a fake transport."""
    s = make_settings(**PROD_BASE, **CLOUD_CREDS, whatsapp_cloud_send_enabled=True)
    transport = RecordingTransport()
    adapter = WhatsAppCloudAdapter(s, httpx.AsyncClient(transport=transport))
    result = await adapter.send_text("+6280000000001", "halo")
    assert result.status == "sent"
    assert result.provider_message_id == "wamid.DUMMY123"
    request = transport.requests[0]
    assert request.url.path.endswith("/000000000000000/messages")
    assert request.headers["Authorization"] == "Bearer dummy-token"

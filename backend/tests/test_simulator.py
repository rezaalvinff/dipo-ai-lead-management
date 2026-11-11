from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import AuditLog, Contact, Lead, Message
from tests.conftest import STRONG_SECRET, make_settings

SIM = "/api/v1/simulator"


async def _create_contact(client, headers, **body):
    body.setdefault("display_name", "Customer Dummy 01")
    response = await client.post(f"{SIM}/contacts", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_contact_auto_and_custom_number(client, admin_headers):
    auto = await _create_contact(client, admin_headers)
    assert auto["phone_number"].startswith("+62800")
    assert auto["is_simulated"] is True

    custom = await _create_contact(
        client, admin_headers, display_name="Dummy 02", phone_number="0800-0000-0002"
    )
    assert custom["phone_number"] == "+6280000000002"

    taken = await client.post(
        f"{SIM}/contacts",
        json={"display_name": "X", "phone_number": "+6280000000002"},
        headers=admin_headers,
    )
    assert taken.status_code == 409

    listed = await client.get(f"{SIM}/contacts", headers=admin_headers)
    assert len(listed.json()) == 2


async def test_real_looking_numbers_are_rejected(client, admin_headers):
    response = await client.post(
        f"{SIM}/contacts",
        json={"display_name": "X", "phone_number": "081234567890"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NOT_A_DUMMY_NUMBER"


async def test_send_message_stores_it_and_ai_replies(client, admin_headers, app):
    contact = await _create_contact(client, admin_headers)
    response = await client.post(
        f"{SIM}/contacts/{contact['id']}/messages", json={"text": "Halo"}, headers=admin_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["duplicate"] is False
    assert body["ai_reply_queued"] is True
    assert body["message"]["direction"] == "inbound"
    assert body["message"]["status"] == "received"

    await client.post(
        f"{SIM}/contacts/{contact['id']}/messages",
        json={"text": "Mau tanya Xpander"},
        headers=admin_headers,
    )

    chat = (await client.get(f"{SIM}/contacts/{contact['id']}/chat", headers=admin_headers)).json()
    assert len(chat["conversations"]) == 1
    messages = chat["conversations"][0]["messages"]
    assert [(m["direction"], m["sender_type"]) for m in messages] == [
        ("inbound", "contact"),
        ("outbound", "ai"),
        ("inbound", "contact"),
        ("outbound", "ai"),
    ]
    assert "nama" in messages[1]["content"]
    assert "Mau tanya Xpander" in messages[3]["content"]
    for m in messages:
        assert m["created_at_wib"].endswith("WIB")
    for m in messages[1::2]:
        assert m["status"] == "sent"
        assert m["provider"] == "simulated"
        assert m["provider_message_id"].startswith("sim-out-")
        assert m["sent_at"] is not None

    # Everything is really in the database, plus a lead and an audit entry.
    async with app.state.ctx.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Message)) == 4
        lead = await session.scalar(select(Lead))
        assert lead.source == "simulator" and lead.is_simulated
        actions = set(await session.scalars(select(AuditLog.action)))
        assert {"simulator.contact_created", "lead.created"} <= actions


async def test_message_status_progression(client, admin_headers):
    contact = await _create_contact(client, admin_headers)
    await client.post(
        f"{SIM}/contacts/{contact['id']}/messages", json={"text": "Halo"}, headers=admin_headers
    )
    chat = (await client.get(f"{SIM}/contacts/{contact['id']}/chat", headers=admin_headers)).json()
    reply = chat["conversations"][0]["messages"][1]

    def set_status(status):
        return client.post(
            f"{SIM}/messages/{reply['id']}/status", json={"status": status}, headers=admin_headers
        )

    delivered = (await set_status("delivered")).json()
    assert delivered["status"] == "delivered" and delivered["delivered_at"]
    read = (await set_status("read")).json()
    assert read["status"] == "read" and read["read_at"]
    # A late "delivered" must not move the status backwards.
    assert (await set_status("delivered")).json()["status"] == "read"

    inbound = chat["conversations"][0]["messages"][0]
    not_allowed = await client.post(
        f"{SIM}/messages/{inbound['id']}/status", json={"status": "read"}, headers=admin_headers
    )
    assert not_allowed.status_code == 404


async def test_new_conversation_closes_old_one(client, admin_headers):
    contact = await _create_contact(client, admin_headers)
    first = (
        await client.post(
            f"{SIM}/contacts/{contact['id']}/messages", json={"text": "Halo"}, headers=admin_headers
        )
    ).json()
    new = await client.post(f"{SIM}/contacts/{contact['id']}/conversations", headers=admin_headers)
    assert new.status_code == 201
    second = (
        await client.post(
            f"{SIM}/contacts/{contact['id']}/messages", json={"text": "Lagi"}, headers=admin_headers
        )
    ).json()
    assert second["conversation_id"] == new.json()["id"] != first["conversation_id"]

    chat = (await client.get(f"{SIM}/contacts/{contact['id']}/chat", headers=admin_headers)).json()
    assert [c["status"] for c in chat["conversations"]] == ["closed", "open"]
    # New conversation starts with a fresh AI greeting.
    assert "nama" in chat["conversations"][1]["messages"][1]["content"]


async def test_delete_and_reset(client, admin_headers, app):
    one = await _create_contact(client, admin_headers)
    await _create_contact(client, admin_headers, display_name="Dummy 02")
    await client.post(
        f"{SIM}/contacts/{one['id']}/messages", json={"text": "Halo"}, headers=admin_headers
    )
    # A non-simulated contact must survive a reset.
    async with app.state.ctx.session_factory() as session:
        session.add(Contact(phone_number="+6289999999999", is_simulated=False))
        await session.commit()

    assert (
        await client.delete(f"{SIM}/contacts/{one['id']}", headers=admin_headers)
    ).status_code == 204
    reset = await client.post(f"{SIM}/reset", headers=admin_headers)
    assert reset.json() == {"deleted_contacts": 1}

    async with app.state.ctx.session_factory() as session:
        remaining = list(await session.scalars(select(Contact.phone_number)))
        assert remaining == ["+6289999999999"]
        assert await session.scalar(select(func.count()).select_from(Message)) == 0


async def test_simulator_routes_absent_in_production():
    settings = make_settings(
        app_env="production", simulator_enabled=False, jwt_secret=STRONG_SECRET
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get(f"{SIM}/contacts")).status_code == 404
            assert (await c.get("/docs")).status_code == 404

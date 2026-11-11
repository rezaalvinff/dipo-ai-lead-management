import uuid

from arq.worker import Worker
from sqlalchemy import select

from app.adapters.whatsapp.cloud import WhatsAppCloudAdapter
from app.core.context import build_context
from app.models import Conversation, Message, User
from app.models.enums import SenderType
from app.services.message_service import MessageService
from app.workers.worker import generate_ai_reply
from tests.conftest import TEST_REDIS_URL, login_headers, make_settings

SIM = "/api/v1/simulator"


async def _contact_with_message(client, headers, text="Halo"):
    contact = (
        await client.post(f"{SIM}/contacts", json={"display_name": "Dummy"}, headers=headers)
    ).json()
    sent = (
        await client.post(
            f"{SIM}/contacts/{contact['id']}/messages", json={"text": text}, headers=headers
        )
    ).json()
    return contact, sent["conversation_id"]


async def test_admin_manual_reply_goes_through_outgoing_service(client, admin_headers):
    _, conversation_id = await _contact_with_message(client, admin_headers)
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"text": "Halo, saya admin (dummy)"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["sender_type"] == "admin"
    assert body["status"] == "sent"
    assert body["provider"] == "simulated"

    history = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=admin_headers
    )
    assert [m["sender_type"] for m in history.json()] == ["contact", "ai", "admin"]


async def test_sales_sees_only_assigned_conversations(client, users, admin_headers, app):
    _, conversation_id = await _contact_with_message(client, admin_headers)
    sales_headers = await login_headers(client, users["sales"])

    assert (await client.get("/api/v1/conversations", headers=sales_headers)).json() == []
    hidden = await client.get(f"/api/v1/conversations/{conversation_id}", headers=sales_headers)
    assert hidden.status_code == 404

    async with app.state.ctx.session_factory() as session:
        sales = await session.scalar(select(User).where(User.email == users["sales"]))
        conversation = await session.get(Conversation, uuid.UUID(conversation_id))
        conversation.assigned_user_id = sales.id
        await session.commit()

    visible = await client.get("/api/v1/conversations", headers=sales_headers)
    assert [c["id"] for c in visible.json()] == [conversation_id]
    reply = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"text": "Halo dari sales dummy"},
        headers=sales_headers,
    )
    assert reply.json()["sender_type"] == "sales"


async def test_blocked_real_delivery_is_stored_as_failed(client, admin_headers, app):
    """If someone wires the Cloud adapter in development, nothing leaves the server."""
    _, conversation_id = await _contact_with_message(client, admin_headers)
    async with app.state.ctx.session_factory() as session:
        conversation = await session.get(Conversation, uuid.UUID(conversation_id))
        service = MessageService(session, WhatsAppCloudAdapter(app.state.ctx.settings))
        message = await service.send_outbound(
            conversation, "should not be sent", sender_type=SenderType.SYSTEM
        )
        await session.commit()
        assert message.status == "failed"
        assert "Blocked" in message.error_detail


async def test_real_worker_processes_queued_ai_reply(users):
    """End-to-end with Redis + ARQ worker instead of the inline queue."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    settings = make_settings(job_queue="arq")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        await app.state.ctx.redis.flushdb()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            headers = await login_headers(client, users["admin"])
            _, conversation_id = await _contact_with_message(client, headers)

            async with app.state.ctx.session_factory() as session:
                rows = list(await session.scalars(select(Message)))
                assert [m.direction for m in rows] == ["inbound"]  # reply not yet generated

            worker_ctx = build_context(settings)

            async def startup(ctx):
                ctx["app"] = worker_ctx

            from arq.connections import RedisSettings

            worker = Worker(
                functions=[generate_ai_reply],
                redis_settings=RedisSettings.from_dsn(TEST_REDIS_URL),
                on_startup=startup,
                burst=True,
                poll_delay=0.1,
            )
            await worker.main()
            assert worker.jobs_complete == 1
            await worker.close()
            await worker_ctx.close()

            history = await client.get(
                f"/api/v1/conversations/{conversation_id}/messages", headers=headers
            )
            assert [m["sender_type"] for m in history.json()] == ["contact", "ai"]

"""Conversation scenarios through the Simulated WhatsApp API (same path as production).

Every scenario sends customer messages exactly like the simulator UI would and
then checks the BACKEND-validated conversation state, handover and replies.
Default AI = MockAIProvider (deterministic). See tests/live/ for real-LLM runs.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.adapters.ai.base import AgentOutput, AgentRequest, AIProviderError, AIResult
from app.models import (
    AIInteraction,
    Conversation,
    KnowledgeBaseArticle,
    User,
    VehicleModel,
    VehicleVariant,
)
from app.services.qualification_service import _amounts
from app.services.settings_service import SETTING_DEFS

SIM = "/api/v1/simulator"
CLOSING = SETTING_DEFS["qualification.closing_message"].default
HUMAN_MSG = SETTING_DEFS["qualification.human_handover_message"].default

VEHICLES = {
    "Xpander": ["xpander", "expander", "xpander ultimate"],
    "Xpander Cross": ["xpander cross", "cross"],
    "Pajero Sport": ["pajero sport", "pajero", "pajsport"],
    "Triton": ["triton"],
    "Xforce": ["xforce", "x force"],
    "L300": ["l300", "l 300"],
}


@pytest.fixture
async def knowledge(app, users):
    """Approved dummy knowledge + items the AI must NOT use (draft, expired)."""
    async with app.state.ctx.session_factory() as session:
        admin = await session.scalar(select(User).where(User.email == users["admin"]))
        models = {}
        for i, (name, aliases) in enumerate(VEHICLES.items()):
            m = VehicleModel(
                name=name,
                aliases=aliases,
                status="approved",
                sort_order=i,
                approved_by_user_id=admin.id,
                approved_at=datetime.now(UTC),
            )
            session.add(m)
            models[name] = m
        await session.flush()
        session.add(
            VehicleVariant(
                vehicle_model_id=models["Xpander"].id,
                name="Ultimate CVT (DUMMY)",
                price_otr=999_000_000,
                price_note="harga contoh, bukan harga asli",
                status="approved",
            )
        )
        session.add_all(
            [
                KnowledgeBaseArticle(
                    title="Jam operasional dealer",
                    category="dealer",
                    status="approved",
                    content="Senin-Sabtu 08.00-17.00 (DATA DUMMY).",
                ),
                KnowledgeBaseArticle(
                    title="Promo rahasia",
                    category="promo",
                    status="draft",
                    content="Diskon 50 juta untuk Xpander.",
                ),
                KnowledgeBaseArticle(
                    title="Promo lama",
                    category="promo",
                    status="approved",
                    content="Cashback 10 juta.",
                    valid_until=datetime.now(UTC) - timedelta(days=1),
                ),
            ]
        )
        await session.commit()
    return models


class Chat:
    def __init__(self, client, headers, contact_id):
        self.client, self.headers, self.contact_id = client, headers, contact_id

    async def say(self, text: str) -> str | None:
        """Send as the customer; return the AI reply to THIS message (None if silent)."""
        before = await self._outbound_ids()
        r = await self.client.post(
            f"{SIM}/contacts/{self.contact_id}/messages", json={"text": text}, headers=self.headers
        )
        assert r.status_code == 201, r.text
        chat = await self.chat()
        new = [
            m
            for c in chat["conversations"]
            for m in c["messages"]
            if m["direction"] == "outbound" and m["id"] not in before
        ]
        assert len(new) <= 1, "AI must send at most one reply per customer message"
        return new[0]["content"] if new else None

    async def chat(self) -> dict:
        r = await self.client.get(f"{SIM}/contacts/{self.contact_id}/chat", headers=self.headers)
        return r.json()

    async def state(self) -> dict:
        return (await self.chat())["state"]

    async def replies(self) -> list[str]:
        chat = await self.chat()
        return [
            m["content"]
            for c in chat["conversations"]
            for m in c["messages"]
            if m["sender_type"] == "ai"
        ]

    async def _outbound_ids(self) -> set[str]:
        chat = await self.chat()
        return {
            m["id"]
            for c in chat["conversations"]
            for m in c["messages"]
            if m["direction"] == "outbound"
        }

    async def asked(self) -> str | None:
        """Which field the backend decided the last reply asks for."""
        return (await self.state())["last_asked_field"]

    async def conversation_id(self) -> str:
        return (await self.chat())["conversations"][-1]["id"]


@pytest.fixture
async def new_chat(client, admin_headers, knowledge):
    async def make(name: str = "Customer Dummy") -> Chat:
        r = await client.post(f"{SIM}/contacts", json={"display_name": name}, headers=admin_headers)
        return Chat(client, admin_headers, r.json()["id"])

    return make


def values(state: dict) -> dict:
    return {k: v["value"] for k, v in state["fields"].items()}


def statuses(state: dict) -> dict:
    return {k: v["status"] for k, v in state["fields"].items()}


def asks(state: dict) -> dict:
    return {k: v["asks"] for k, v in state["fields"].items()}


def amounts_in(text: str) -> set[int]:
    return _amounts(text)


# =========================================================== 1-3: happy paths
async def test_s01_user_example_flow(new_chat):
    """Contoh dari brief. Xpander sudah disebut di awal, jadi unit tidak ditanya lagi."""
    chat = await new_chat()
    r1 = await chat.say("Halo, saya mau tanya Xpander.")
    assert "selamat datang" in r1.lower()
    assert await chat.asked() == "name"
    r2 = await chat.say("Andi.")
    assert "Andi" in r2
    assert await chat.asked() == "domicile"
    assert await chat.say("Medan.") == CLOSING
    state = await chat.state()
    assert values(state) == {"name": "Andi", "domicile": "Medan", "vehicle": "Xpander"}
    assert state["handler"] == "admin_queue" and state["stage"] == "handed_over"
    assert state["handover_reason"] == "qualification_complete"
    assert state["lead_status"] == "qualified"
    assert asks(state)["vehicle"] == 0  # never asked: already answered


async def test_s02_one_by_one(new_chat):
    chat = await new_chat()
    await chat.say("Halo")
    assert await chat.asked() == "name"
    await chat.say("Budi")
    assert await chat.asked() == "domicile"
    await chat.say("Bekasi")
    assert await chat.asked() == "vehicle"
    assert await chat.say("Pajero Sport") == CLOSING
    state = await chat.state()
    assert asks(state) == {"name": 1, "domicile": 1, "vehicle": 1}  # one question each
    assert values(state) == {"name": "Budi", "domicile": "Bekasi", "vehicle": "Pajero Sport"}


async def test_s03_all_info_in_one_message(new_chat):
    chat = await new_chat()
    reply = await chat.say("Halo, saya Rina dari Surabaya, mau tanya Pajero Sport")
    assert reply == CLOSING
    state = await chat.state()
    assert values(state) == {"name": "Rina", "domicile": "Surabaya", "vehicle": "Pajero Sport"}
    assert state["handover_reason"] == "qualification_complete"


# =========================================================== 4-5: corrections
async def test_s04_customer_changes_unit(new_chat):
    chat = await new_chat()
    await chat.say("Halo mau tanya Xpander")
    await chat.say("Doni")
    assert await chat.say("eh ganti deh, saya mau Pajero Sport aja. Saya di Depok") == CLOSING
    state = await chat.state()
    assert values(state)["vehicle"] == "Pajero Sport"
    corrections = [h for h in state["history"] if h["type"] == "correction"]
    assert [(c["field"], c["old"], c["new"]) for c in corrections] == [
        ("vehicle", "Xpander", "Pajero Sport")
    ]


async def test_s05_customer_corrects_domicile(new_chat):
    chat = await new_chat()
    await chat.say("Halo")
    await chat.say("Sari")
    await chat.say("Medan")
    assert await chat.asked() == "vehicle"
    await chat.say("eh maaf salah, saya di Binjai bukan Medan")
    state = await chat.state()
    assert values(state)["domicile"] == "Binjai"
    assert state["last_asked_field"] == "vehicle"  # domicile not asked again
    assert asks(state)["domicile"] == 1
    assert await chat.say("Triton") == CLOSING
    assert values(await chat.state()) == {"name": "Sari", "domicile": "Binjai", "vehicle": "Triton"}


# =========================================================== 6-7: not answering / refusing
async def test_s06_customer_does_not_answer(new_chat):
    """Ditanya nama 2x tanpa jawaban: tidak dipaksa, lanjut ke domisili."""
    chat = await new_chat()
    await chat.say("Halo")
    await chat.say("ok")
    assert await chat.asked() == "name"  # 2nd (and last) time
    await chat.say("iya")
    state = await chat.state()
    assert state["last_asked_field"] == "domicile"
    assert statuses(state)["name"] == "declined"
    assert asks(state)["name"] == 2


async def test_s07_customer_refuses_name_is_not_forced(new_chat):
    chat = await new_chat()
    await chat.say("Halo")
    await chat.say("ga mau kasih nama ah")
    assert await chat.asked() == "domicile"
    await chat.say("Medan")
    assert await chat.say("Xpander") == CLOSING
    state = await chat.state()
    assert statuses(state) == {"name": "declined", "domicile": "collected", "vehicle": "collected"}
    assert asks(state)["name"] == 1  # asked once, never again
    assert state["handover_reason"] == "partial_data"
    assert state["lead_status"] == "qualifying"  # backend: incomplete != qualified


# =========================================================== 8-10: knowledge base
async def test_s08_promo_not_available_is_not_invented(new_chat):
    chat = await new_chat()
    reply = await chat.say("Halo, ada promo Xpander bulan ini?")
    assert not amounts_in(reply)  # no invented numbers at all
    for forbidden in ("50 juta", "10 juta", "diskon 50", "cashback 10"):
        assert forbidden not in reply.lower()  # draft + expired promos never reach the AI
    state = await chat.state()
    assert state["last_asked_field"] == "name"  # still continues collecting
    assert values(state)["vehicle"] == "Xpander"


async def test_s09_answers_from_approved_knowledge(new_chat):
    chat = await new_chat()
    reply = await chat.say("Halo kak, dealer buka jam berapa ya?")
    assert "08.00" in reply and "17.00" in reply
    assert await chat.asked() == "name"


async def test_s10_price_from_approved_variant_only(new_chat):
    chat = await new_chat()
    await chat.say("Halo saya Andi")
    reply = await chat.say("mau tanya harga xpander dong")
    assert amounts_in(reply) <= {999_000_000}  # only the approved (dummy) price
    assert 999_000_000 in amounts_in(reply)
    assert await chat.asked() == "domicile"  # remembers the name


# =========================================================== 11-12: informal & typos
async def test_s11_informal_language_and_typos(new_chat):
    chat = await new_chat()
    await chat.say("hlo kak, sy mw tny expander")
    assert await chat.asked() == "name"
    await chat.say("panggil aja jo")
    assert await chat.say("dr bks") == CLOSING
    assert values(await chat.state()) == {"name": "Jo", "domicile": "Bekasi", "vehicle": "Xpander"}


async def test_s12_typo_in_model_name(new_chat):
    chat = await new_chat()
    assert await chat.say("Halo, saya Tono di Medan, minat pajero sprot") == CLOSING
    assert values(await chat.state())["vehicle"] == "Pajero Sport"


# =========================================================== 13-14: humans
async def test_s13_customer_requests_human(new_chat):
    chat = await new_chat()
    await chat.say("Halo")
    assert await chat.say("saya mau bicara dengan sales langsung") == HUMAN_MSG
    state = await chat.state()
    assert state["handler"] == "admin_queue" and state["handover_reason"] == "human_requested"
    assert await chat.say("halo? masih ada orang?") is None  # AI stays silent


async def test_s14_human_takeover_stops_ai_and_can_return(new_chat, client, admin_headers):
    chat = await new_chat()
    await chat.say("Halo, saya Lina")
    conversation_id = await chat.conversation_id()
    r = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"text": "Halo Bu Lina, saya admin (dummy)."},
        headers=admin_headers,
    )
    assert r.status_code == 201
    assert await chat.say("Oh halo admin") is None  # AI must not reply after takeover
    state = await chat.state()
    assert state["handler"] == "admin" and state["handover_reason"] == "manual_takeover"

    r = await client.post(
        f"/api/v1/conversations/{conversation_id}/handler",
        json={"handler": "ai"},
        headers=admin_headers,
    )
    assert r.json()["handler"] == "ai"
    assert await chat.say("saya di Depok") is not None
    state = await chat.state()
    assert values(state)["name"] == "Lina" and values(state)["domicile"] == "Depok"
    assert state["last_asked_field"] == "vehicle"  # name not asked again


# =========================================================== 15-18: settings & validation
async def test_s15_closing_message_is_editable(new_chat, client, admin_headers):
    r = await client.put(
        "/api/v1/settings/qualification.closing_message",
        json={"value": "Terima kasih {nama}! Info {unit} segera dikirim tim sales."},
        headers=admin_headers,
    )
    assert r.status_code == 200
    chat = await new_chat()
    reply = await chat.say("Halo saya Rudi dari Bandung mau Triton")
    assert reply == "Terima kasih Rudi! Info Triton segera dikirim tim sales."


async def test_s16_returning_customer_is_not_asked_again(new_chat, client, admin_headers):
    chat = await new_chat()
    await chat.say("Halo saya Rudi dari Bandung mau Triton")
    await client.post(f"{SIM}/contacts/{chat.contact_id}/conversations", headers=admin_headers)
    reply = await chat.say("halo, saya chat lagi")
    assert reply == SETTING_DEFS["qualification.returning_customer_message"].default
    state = await chat.state()
    assert state["handover_reason"] == "returning_customer"
    assert asks(state) == {"name": 0, "domicile": 0, "vehicle": 0}


async def test_s17_vehicle_outside_catalog_is_rejected(new_chat):
    chat = await new_chat()
    await chat.say("Halo saya Ani")
    await chat.say("Depok")
    await chat.say("Avanza")
    state = await chat.state()
    assert values(state)["vehicle"] is None
    assert state["last_asked_field"] == "vehicle"
    assert await chat.say("oke kalau gitu Xforce") == CLOSING


async def test_s18_invalid_domicile_is_asked_politely_again(new_chat):
    chat = await new_chat()
    await chat.say("Halo")
    await chat.say("Budi")
    await chat.say("rumah")
    state = await chat.state()
    assert values(state)["domicile"] is None
    assert state["last_asked_field"] == "domicile"


# =========================================================== 19-22: backend guards
class StubProvider:
    """Replaces the AI to simulate misbehaviour of a real LLM."""

    name, model = "stub", "stub-1"

    def __init__(self, fn):
        self.fn = fn
        self.calls = 0

    async def run_turn(self, req: AgentRequest) -> AIResult:
        self.calls += 1
        return AIResult(output=await self.fn(req), provider=self.name, model=self.model)


def stub_output(**kw) -> AgentOutput:
    base = dict(
        customer_name="",
        domicile="",
        vehicle_model="",
        declined_fields=[],
        intent="other",
        asked_field="name",
        reply="",
    )
    return AgentOutput(**(base | kw))


async def test_s19_fabricated_price_is_blocked(new_chat, app):
    async def lie(req):
        return stub_output(
            reply="Harga Xpander cuma Rp 150.000.000 dan diskon 20 juta! Siapa nama Anda?"
        )

    app.state.ctx.ai = StubProvider(lie)
    chat = await new_chat()
    reply = await chat.say("berapa harga xpander?")
    assert "150.000.000" not in reply and "20 juta" not in reply
    assert "belum ada informasi" in reply  # backend template replaced the AI draft
    assert await chat.asked() == "name"
    async with app.state.ctx.session_factory() as session:
        log = await session.scalar(select(AIInteraction))
        assert log.decision["guard_blocked"] == [20_000_000, 150_000_000]


async def test_s20_backend_decides_completeness_not_ai(new_chat, app):
    """AI claims everything is done, but the name is invalid -> no handover."""

    async def overconfident(req):
        return stub_output(
            customer_name="ok",
            domicile="Medan",
            vehicle_model="Xpander",
            intent="provide_info",
            asked_field="none",
            reply="Sudah lengkap!",
        )

    app.state.ctx.ai = StubProvider(overconfident)
    chat = await new_chat()
    reply = await chat.say("ok")
    state = await chat.state()
    assert state["handler"] == "ai" and state["lead_status"] != "qualified"
    assert statuses(state)["name"] == "missing"
    assert reply.startswith("Halo! Selamat datang") and "nama" in reply


async def test_s21_ai_failure_falls_back_then_hands_over(new_chat, app):
    async def broken(req):
        raise AIProviderError("simulated outage")

    app.state.ctx.ai = StubProvider(broken)
    chat = await new_chat()
    assert await chat.say("Halo") is not None  # template question, customer not ignored
    assert await chat.asked() == "name"
    assert await chat.say("halo?") is not None
    reply = await chat.say("halo??")
    assert reply == SETTING_DEFS["qualification.ai_unavailable_message"].default
    assert (await chat.state())["handover_reason"] == "ai_unavailable"


async def test_s22_takeover_during_ai_generation_discards_reply(new_chat, app):
    async def slow(req):
        # A human takes over while the AI is still "thinking".
        async with app.state.ctx.session_factory() as session:
            for conv in await session.scalars(select(Conversation)):
                conv.handler = "admin"
            await session.commit()
        return stub_output(reply="Boleh tahu nama Anda?", asked_field="name")

    app.state.ctx.ai = StubProvider(slow)
    chat = await new_chat()
    assert await chat.say("Halo") is None


async def test_s23_ai_disabled_by_admin(new_chat, client, admin_headers):
    await client.put("/api/v1/settings/ai.enabled", json={"value": False}, headers=admin_headers)
    chat = await new_chat()
    assert await chat.say("Halo") is None
    state = await chat.state()
    assert state["handler"] == "admin_queue" and state["handover_reason"] == "ai_disabled"


async def test_s24_only_one_reply_for_burst_messages(app, new_chat):
    """3 quick messages queued before the worker runs -> only the newest is answered."""
    from app.workers.tasks import process_ai_reply

    class DeferredQueue:
        def __init__(self):
            self.ids: list[uuid.UUID] = []

        async def enqueue_ai_reply(self, message_id):
            self.ids.append(message_id)

        async def close(self):
            pass

    queue = DeferredQueue()
    app.state.ctx.queue = queue
    chat = await new_chat()
    for text in ("Halo", "saya Andi", "dari Medan"):
        await chat.say(text)
    for message_id in queue.ids:
        await process_ai_reply(app.state.ctx, message_id)
    assert len(await chat.replies()) == 1
    assert values(await chat.state())["name"] == "Andi"

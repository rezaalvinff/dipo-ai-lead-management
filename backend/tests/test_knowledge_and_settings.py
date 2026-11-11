from datetime import UTC, datetime, timedelta

from tests.conftest import login_headers

KB = "/api/v1/knowledge"


async def test_knowledge_crud_and_approval_controls_ai_context(client, admin_headers):
    # Create a model as draft -> invisible to the AI.
    r = await client.post(
        f"{KB}/vehicle-models",
        headers=admin_headers,
        json={"name": "Xpander", "aliases": ["Expander", " xpander "]},
    )
    assert r.status_code == 201
    model = r.json()
    assert model["status"] == "draft" and model["aliases"] == ["expander", "xpander"]
    preview = (await client.get(f"{KB}/ai-context", headers=admin_headers)).json()
    assert preview["vehicle_models"] == []

    # Approve -> visible.
    r = await client.patch(
        f"{KB}/vehicle-models/{model['id']}", headers=admin_headers, json={"status": "approved"}
    )
    assert r.json()["status"] == "approved" and r.json()["approved_by_user_id"]
    assert (await client.get(f"{KB}/ai-context", headers=admin_headers)).json()[
        "vehicle_models"
    ] == ["Xpander"]

    # Variant with specs & price.
    r = await client.post(
        f"{KB}/vehicle-models/{model['id']}/variants",
        headers=admin_headers,
        json={
            "name": "Exceed MT (DUMMY)",
            "transmission": "Manual",
            "specs": {"Kursi": "7"},
            "price_otr": 123456000,
            "price_note": "contoh",
            "status": "approved",
        },
    )
    assert r.status_code == 201
    variant = r.json()

    # Promo, DP, angsuran, FAQ, dealer articles.
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    for category, title, content in [
        ("promo", "Promo DUMMY", "Gratis kaca film (contoh)."),
        ("dp", "DP DUMMY", "DP mulai 20% (contoh)."),
        ("installment", "Angsuran DUMMY", "Tenor sampai 60 bulan (contoh)."),
        ("faq", "Test drive", "Bisa test drive di dealer (contoh)."),
        ("dealer", "Alamat", "Jl. Contoh No. 1 (contoh)."),
    ]:
        r = await client.post(
            f"{KB}/articles",
            headers=admin_headers,
            json={
                "title": title,
                "category": category,
                "content": content,
                "status": "approved",
                "valid_until": future,
                "vehicle_model_id": model["id"],
            },
        )
        assert r.status_code == 201, r.text

    text = (await client.get(f"{KB}/ai-context", headers=admin_headers)).json()["text"]
    for expected in (
        "Rp 123.456.000",
        "Kursi: 7",
        "Gratis kaca film",
        "DP mulai 20%",
        "60 bulan",
        "test drive",
        "Jl. Contoh",
        "## PROMO",
        "## INFORMASI DEALER",
    ):
        assert expected in text

    # Editing approved content sends it back to draft (needs re-approval).
    r = await client.patch(
        f"/api/v1/knowledge/variants/{variant['id']}",
        headers=admin_headers,
        json={"price_otr": 111000000},
    )
    assert r.json()["status"] == "draft"
    assert (
        "Rp 111.000.000"
        not in (await client.get(f"{KB}/ai-context", headers=admin_headers)).json()["text"]
    )

    # Delete.
    articles = (await client.get(f"{KB}/articles?category=promo", headers=admin_headers)).json()
    r = await client.delete(f"{KB}/articles/{articles[0]['id']}", headers=admin_headers)
    assert r.status_code == 204
    assert (
        "Gratis kaca film"
        not in (await client.get(f"{KB}/ai-context", headers=admin_headers)).json()["text"]
    )
    assert (
        await client.delete(f"{KB}/vehicle-models/{model['id']}", headers=admin_headers)
    ).status_code == 204


async def test_knowledge_permissions(client, users):
    supervisor = await login_headers(client, users["supervisor"])
    sales = await login_headers(client, users["sales"])
    body = {"name": "Triton"}
    assert (await client.get(f"{KB}/vehicle-models", headers=supervisor)).status_code == 200
    assert (
        await client.post(f"{KB}/vehicle-models", json=body, headers=supervisor)
    ).status_code == 403
    assert (await client.get(f"{KB}/vehicle-models", headers=sales)).status_code == 403


async def test_duplicate_model_rejected(client, admin_headers):
    await client.post(f"{KB}/vehicle-models", json={"name": "Triton"}, headers=admin_headers)
    r = await client.post(f"{KB}/vehicle-models", json={"name": "Triton"}, headers=admin_headers)
    assert r.status_code == 409


async def test_settings_validation_and_reset(client, admin_headers, users):
    listed = (await client.get("/api/v1/settings", headers=admin_headers)).json()
    assert {s["key"] for s in listed} >= {"qualification.closing_message", "ai.enabled"}

    key = "/api/v1/settings/qualification.closing_message"
    bad = await client.put(key, json={"value": "Halo {password}"}, headers=admin_headers)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVALID_PLACEHOLDER"
    assert (await client.put(key, json={"value": ""}, headers=admin_headers)).status_code == 400
    assert (
        await client.put(
            "/api/v1/settings/qualification.max_asks_per_field",
            json={"value": 9},
            headers=admin_headers,
        )
    ).status_code == 400

    ok = await client.put(key, json={"value": "Terima kasih {nama}."}, headers=admin_headers)
    assert ok.json()["value"] == "Terima kasih {nama}." and ok.json()["is_default"] is False
    reset = await client.delete(key, headers=admin_headers)
    assert reset.json()["is_default"] is True

    supervisor = await login_headers(client, users["supervisor"])
    assert (await client.put(key, json={"value": "x"}, headers=supervisor)).status_code == 403

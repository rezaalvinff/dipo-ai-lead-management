from app.api.deps import ACCESS_COOKIE
from tests.conftest import DUMMY_PASSWORD, login_headers, make_settings


async def test_health_ok(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "ok", "redis": "ok"}
    assert body["providers"]["whatsapp"] == "simulated"


async def test_health_reports_broken_redis():
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app(make_settings(redis_url="redis://localhost:1/0"))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            response = await c.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "error"


async def test_login_success_sets_cookie(client, users):
    response = await client.post(
        "/api/v1/auth/login", json={"email": users["admin"], "password": DUMMY_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["user"]["role_name"] == "admin"
    assert ACCESS_COOKIE in response.cookies


async def test_login_wrong_password(client, users):
    response = await client.post(
        "/api/v1/auth/login", json={"email": users["admin"], "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_with_bearer_and_cookie(client, users):
    headers = await login_headers(client, users["sales"])
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["role_name"] == "sales"
    # Cookie from the login above also works.
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200


async def test_me_requires_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_invalid_token_rejected(client):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc.def"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


async def test_rbac_only_admin_creates_users(client, users):
    payload = {
        "email": "new.sales@example.com",
        "full_name": "Sales Baru Dummy",
        "password": DUMMY_PASSWORD,
        "role": "sales",
    }
    sales = await login_headers(client, users["sales"])
    assert (await client.post("/api/v1/users", json=payload, headers=sales)).status_code == 403

    supervisor = await login_headers(client, users["supervisor"])
    assert (await client.post("/api/v1/users", json=payload, headers=supervisor)).status_code == 403

    admin = await login_headers(client, users["admin"])
    response = await client.post("/api/v1/users", json=payload, headers=admin)
    assert response.status_code == 201
    assert response.json()["role_name"] == "sales"

    duplicate = await client.post("/api/v1/users", json=payload, headers=admin)
    assert duplicate.status_code == 409


async def test_rbac_sales_cannot_use_simulator(client, users):
    sales = await login_headers(client, users["sales"])
    response = await client.get("/api/v1/simulator/contacts", headers=sales)
    assert response.status_code == 403

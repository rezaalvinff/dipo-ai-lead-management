"""Test setup: a real PostgreSQL test database + Redis, all data is dummy.

Defaults match a local dev machine; override with TEST_DATABASE_URL / TEST_REDIS_URL.
"""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import Settings
from app.main import create_app
from app.models import Base
from app.services.auth_service import UserService

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://dipo:dipo@localhost:5432/dipo_test"
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

TEST_APP_SECRET = "dummy-app-secret-for-tests"
TEST_VERIFY_TOKEN = "dummy-verify-token-for-tests"
DUMMY_PASSWORD = "Password-Dummy-123"
STRONG_SECRET = "x9Kq2LmZ7vRt4WbN8cYp3HsJ6dFg1QaE"  # fictional, tests only


def alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


def make_settings(**overrides) -> Settings:
    values = {
        "database_url": TEST_DATABASE_URL,
        "redis_url": TEST_REDIS_URL,
        "job_queue": "inline",
        "whatsapp_app_secret": TEST_APP_SECRET,
        "whatsapp_webhook_verify_token": TEST_VERIFY_TOKEN,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables(migrated_database):
    yield
    engine = create_engine(TEST_DATABASE_URL)
    tables = [t.name for t in Base.metadata.sorted_tables if t.name != "roles"]
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    engine.dispose()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def app(settings):
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def users(app) -> dict[str, str]:
    """Create one dummy user per role. Returns role -> email."""
    emails = {}
    async with app.state.ctx.session_factory() as session:
        service = UserService(session)
        for role in ("admin", "supervisor", "sales"):
            email = f"{role}.dummy@example.com"
            await service.create_user(
                email=email, full_name=f"{role.title()} Dummy", password=DUMMY_PASSWORD, role=role
            )
            emails[role] = email
    return emails


async def login_headers(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DUMMY_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def admin_headers(client, users):
    return await login_headers(client, users["admin"])

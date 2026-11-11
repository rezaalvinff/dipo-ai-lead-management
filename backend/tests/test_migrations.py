from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.models import Base
from tests.conftest import TEST_DATABASE_URL, alembic_config

EXPECTED_TABLES = {
    "roles",
    "users",
    "agent_profiles",
    "territories",
    "territory_mappings",
    "contacts",
    "campaigns",
    "leads",
    "assignments",
    "conversations",
    "messages",
    "knowledge_base_articles",
    "conversion_events",
    "audit_logs",
    "webhook_events",
}


def _tables() -> set[str]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_all_tables_exist_after_upgrade():
    assert EXPECTED_TABLES <= _tables()
    # Models and migration describe the same tables.
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_roles_are_seeded_by_migration():
    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        names = {row[0] for row in conn.execute(text("SELECT name FROM roles"))}
    engine.dispose()
    assert names == {"admin", "supervisor", "sales"}


def test_downgrade_then_upgrade_again():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    assert not (EXPECTED_TABLES & _tables())
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= _tables()


def test_models_match_migration():
    """Autogenerate must find no differences between models and the database."""
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    assert diff == []

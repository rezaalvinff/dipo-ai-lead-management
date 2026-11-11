"""Seed DUMMY development data:  python -m app.scripts.seed

Creates an admin, a supervisor, two sales agents, sample territories, the
Mitsubishi model catalog (names only, approved) and DRAFT knowledge placeholders.
Every name/email/phone here is fictional.
Refuses to run in production.
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from app.core.logging import configure_logging
from app.models import (
    AgentProfile,
    KnowledgeBaseArticle,
    Territory,
    TerritoryMapping,
    User,
    VehicleModel,
)
from app.models.enums import KnowledgeStatus, RoleName
from app.services.auth_service import UserService

logger = logging.getLogger("seed")

DUMMY_USERS = [
    ("Admin Dummy", "admin", None),
    ("Supervisor Dummy", "supervisor", None),
    ("Sales Medan Dummy", "sales", "+6280000009001"),
    ("Sales Jakarta Dummy", "sales", "+6280000009002"),
    ("Sales Pekanbaru Dummy", "sales", "+6280000009003"),
    ("Sales Surabaya Dummy", "sales", "+6280000009004"),
    ("Sales Padang Dummy", "sales", "+6280000009005"),
]

# Exact mapped areas only; nearby cities are never inferred.
TERRITORIES = {
    "Medan": ["medan kota"],
    "Jakarta": ["dki jakarta"],
    "Pekanbaru": ["pekan baru"],
    "Surabaya": ["sby"],
    "Padang": ["kota padang"],
}

# Article placeholders are DRAFT: the AI never sees them until an admin
# replaces the text with official information and approves it.
KNOWLEDGE = [
    ("Jam operasional dealer", "dealer", "PLACEHOLDER - isi dengan jam operasional resmi."),
    ("Alamat dealer", "dealer", "PLACEHOLDER - isi dengan alamat resmi."),
    ("Apakah bisa test drive?", "faq", "PLACEHOLDER - isi dengan jawaban resmi."),
]

# Model names + common informal spellings/typos. Names only: NO prices/promos,
# those must come from official dealer data entered by an admin.
VEHICLE_MODELS = {
    "Xpander": ["xpander", "expander", "xpender", "x pander"],
    "Xpander Cross": ["xpander cross", "expander cross", "cross"],
    "Xforce": ["xforce", "x force", "x-force"],
    "Pajero Sport": ["pajero sport", "pajero", "pajsport", "pajero sprot"],
    "Destinator": ["destinator"],
    "Triton": ["triton", "strada triton"],
    "L300": ["l300", "l 300", "elteri"],
    "L100 EV": ["l100", "l100 ev", "l 100"],
}


def _email(name: str, role: str, admin_email: str) -> str:
    if role == RoleName.ADMIN:
        return admin_email
    return name.lower().replace(" ", ".") + "@example.com"


async def seed() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.is_production:
        raise SystemExit("Seed data dummy tidak boleh dijalankan di production.")
    if len(settings.seed_default_password) < 8:
        raise SystemExit(
            "Isi SEED_DEFAULT_PASSWORD (min. 8 karakter) di file .env terlebih dahulu."
        )

    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        users = UserService(session)
        for name, role, phone in DUMMY_USERS:
            email = _email(name, role, settings.seed_admin_email)
            if await session.scalar(select(User).where(User.email == email)):
                logger.info("User exists, skip: %s", email)
                continue
            await users.create_user(
                email=email,
                full_name=name,
                password=settings.seed_default_password,
                role=role,
                agent_phone=phone,
            )
            logger.info("Created %s user: %s", role, email)

        territories: dict[str, Territory] = {}
        for name, aliases in TERRITORIES.items():
            territory = await session.scalar(select(Territory).where(Territory.name == name))
            if territory is None:
                territory = Territory(name=name, aliases=aliases)
                session.add(territory)
            territories[name] = territory
        await session.flush()

        # Ensure the five regional dummy agents are mapped to their exact territory.
        # Existing mappings are preserved; seed can safely be run more than once.
        for territory_name, agent_name in (
            ("Medan", "Sales Medan Dummy"),
            ("Jakarta", "Sales Jakarta Dummy"),
            ("Pekanbaru", "Sales Pekanbaru Dummy"),
            ("Surabaya", "Sales Surabaya Dummy"),
            ("Padang", "Sales Padang Dummy"),
        ):
            agent_user = await session.scalar(select(User).where(User.full_name == agent_name))
            if agent_user is None or agent_user.agent_profile is None:
                continue
            territory = territories[territory_name]
            exists = await session.scalar(select(TerritoryMapping.id).where(
                TerritoryMapping.territory_id == territory.id,
                TerritoryMapping.agent_profile_id == agent_user.agent_profile.id,
            ))
            if exists is None:
                session.add(TerritoryMapping(
                    territory_id=territory.id,
                    agent_profile_id=agent_user.agent_profile.id,
                    priority=1,
                ))

        admin = await session.scalar(select(User).where(User.email == settings.seed_admin_email))
        for order, (name, aliases) in enumerate(VEHICLE_MODELS.items()):
            if await session.scalar(select(VehicleModel.id).where(VehicleModel.name == name)):
                continue
            session.add(
                VehicleModel(
                    name=name,
                    aliases=aliases,
                    sort_order=order,
                    status=KnowledgeStatus.APPROVED,
                    approved_by_user_id=admin.id if admin else None,
                    approved_at=datetime.now(UTC),
                )
            )

        if not await session.scalar(select(KnowledgeBaseArticle.id).limit(1)):
            for title, category, content in KNOWLEDGE:
                session.add(
                    KnowledgeBaseArticle(
                        title=title,
                        category=category,
                        content=content,
                        status=KnowledgeStatus.DRAFT,
                    )
                )

        await session.commit()
    await engine.dispose()
    logger.info("Seed selesai.")


if __name__ == "__main__":
    asyncio.run(seed())

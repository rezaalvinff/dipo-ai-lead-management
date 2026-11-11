"""Seed DUMMY development data:  python -m app.scripts.seed

Creates an admin, a supervisor, two sales agents, sample territories and
knowledge-base placeholders. Every name/email/phone here is fictional.
Refuses to run in production.
"""

import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from app.core.logging import configure_logging
from app.models import AgentProfile, KnowledgeBaseArticle, Territory, TerritoryMapping, User
from app.models.enums import RoleName
from app.services.auth_service import UserService

logger = logging.getLogger("seed")

DUMMY_USERS = [
    ("Admin Dummy", "admin", None),
    ("Supervisor Dummy", "supervisor", None),
    ("Sales Dummy Satu", "sales", "+6280000009001"),
    ("Sales Dummy Dua", "sales", "+6280000009002"),
]

TERRITORIES = {
    "Jakarta Selatan": ["jaksel", "jakarta selatan", "jkt selatan"],
    "Bekasi": ["bekasi", "bks"],
    "Depok": ["depok"],
}

KNOWLEDGE = [
    ("Contoh FAQ: Jam operasional", "faq", "Isi placeholder. Ganti dengan informasi resmi."),
    ("Contoh unit kendaraan", "vehicle", "Isi placeholder. Ganti dengan data unit resmi."),
]


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

        agents = list(await session.scalars(select(AgentProfile).order_by(AgentProfile.created_at)))
        if agents and not await session.scalar(select(TerritoryMapping.id).limit(1)):
            names = list(territories)
            for index, name in enumerate(names):
                agent = agents[index % len(agents)]
                session.add(
                    TerritoryMapping(territory_id=territories[name].id, agent_profile_id=agent.id)
                )

        if not await session.scalar(select(KnowledgeBaseArticle.id).limit(1)):
            for title, category, content in KNOWLEDGE:
                session.add(KnowledgeBaseArticle(title=title, category=category, content=content))

        await session.commit()
    await engine.dispose()
    logger.info("Seed selesai.")


if __name__ == "__main__":
    asyncio.run(seed())

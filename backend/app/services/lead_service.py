from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, Lead
from app.models.enums import LeadSource, LeadStatus, LeadTemperature

CLOSED_LEAD_STATUSES = (LeadStatus.WON, LeadStatus.LOST)


class LeadService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_for_contact(self, contact: Contact) -> Lead | None:
        return await self.session.scalar(
            select(Lead)
            .where(Lead.contact_id == contact.id, Lead.status.not_in(CLOSED_LEAD_STATUSES))
            .order_by(Lead.created_at.desc())
            .limit(1)
        )

    async def get_or_create_active(
        self, contact: Contact, *, source: LeadSource, referral: dict | None = None
    ) -> tuple[Lead, bool]:
        lead = await self.get_active_for_contact(contact)
        if lead:
            return lead, False
        lead = Lead(
            contact_id=contact.id,
            source=LeadSource.CTWA_AD if referral else source,
            ad_referral=referral,
            status=LeadStatus.NEW,
            temperature=LeadTemperature.COLD,
            is_simulated=contact.is_simulated,
        )
        self.session.add(lead)
        await self.session.flush()
        return lead, True

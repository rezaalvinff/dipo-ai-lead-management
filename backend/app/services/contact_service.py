from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact


class ContactService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_phone(self, phone: str) -> Contact | None:
        return await self.session.scalar(select(Contact).where(Contact.phone_number == phone))

    async def get_or_create(
        self,
        phone: str,
        *,
        display_name: str | None = None,
        wa_id: str | None = None,
        is_simulated: bool = False,
    ) -> Contact:
        # INSERT ... ON CONFLICT DO NOTHING is safe when two webhooks arrive at once.
        await self.session.execute(
            insert(Contact)
            .values(
                phone_number=phone,
                display_name=display_name,
                wa_id=wa_id,
                is_simulated=is_simulated,
            )
            .on_conflict_do_nothing(index_elements=[Contact.phone_number])
        )
        contact = await self.get_by_phone(phone)
        if contact is None:  # pragma: no cover - insert above guarantees a row
            raise RuntimeError("Contact upsert failed")
        if display_name and not contact.display_name:
            contact.display_name = display_name
        if wa_id and not contact.wa_id:
            contact.wa_id = wa_id
        return contact

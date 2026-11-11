"""Simulated WhatsApp: a thin layer that only builds InboundMessage/StatusUpdate
objects and hands them to the SAME services used in production."""

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.whatsapp.base import InboundMessage, StatusUpdate
from app.adapters.whatsapp.simulated import new_simulated_message_id
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.phone import SIMULATED_PHONE_PREFIX, is_simulated_phone, normalize_phone
from app.models import Contact, Conversation, Message
from app.models.enums import ActorType, LeadSource, MessageDirection, ProviderName
from app.services.audit_service import record_audit
from app.services.conversation_service import ConversationService
from app.services.inbound_service import InboundMessageService, InboundResult
from app.services.lead_service import LeadService
from app.services.message_service import MessageService
from app.workers.queue import JobQueue

SIMULATED_STATUSES = {"sent", "delivered", "read", "failed"}


class SimulatorService:
    def __init__(self, session: AsyncSession, settings: Settings, queue: JobQueue):
        self.session = session
        self.settings = settings
        self.queue = queue

    # --- contacts -------------------------------------------------------
    async def list_contacts(self) -> list[Contact]:
        rows = await self.session.scalars(
            select(Contact).where(Contact.is_simulated.is_(True)).order_by(Contact.created_at)
        )
        return list(rows)

    async def get_contact(self, contact_id: uuid.UUID) -> Contact:
        contact = await self.session.get(Contact, contact_id)
        if contact is None or not contact.is_simulated:
            raise NotFoundError("Customer dummy tidak ditemukan", code="SIM_CONTACT_NOT_FOUND")
        return contact

    async def _generate_phone(self) -> str:
        for _ in range(20):
            candidate = SIMULATED_PHONE_PREFIX + f"{secrets.randbelow(10**8):08d}"
            exists = await self.session.scalar(
                select(Contact.id).where(Contact.phone_number == candidate)
            )
            if not exists:
                return candidate
        raise AppError("Gagal membuat nomor dummy, coba lagi")

    async def create_contact(
        self, display_name: str, phone_number: str | None, actor_user_id: uuid.UUID
    ) -> Contact:
        if phone_number:
            try:
                phone = normalize_phone(phone_number)
            except ValueError as exc:
                raise AppError(str(exc), code="INVALID_PHONE") from exc
            if not is_simulated_phone(phone):
                raise AppError(
                    f"Nomor dummy wajib diawali {SIMULATED_PHONE_PREFIX} "
                    "agar tidak bentrok dengan nomor asli",
                    code="NOT_A_DUMMY_NUMBER",
                )
        else:
            phone = await self._generate_phone()

        contact = Contact(phone_number=phone, display_name=display_name, is_simulated=True)
        self.session.add(contact)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Nomor dummy sudah dipakai", code="PHONE_TAKEN") from exc
        record_audit(
            self.session,
            action="simulator.contact_created",
            entity_type="contact",
            entity_id=contact.id,
            actor_type=ActorType.USER,
            actor_user_id=actor_user_id,
        )
        await self.session.commit()
        return contact

    async def delete_contact(self, contact_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
        contact = await self.get_contact(contact_id)
        await self.session.delete(contact)
        record_audit(
            self.session,
            action="simulator.contact_deleted",
            entity_type="contact",
            entity_id=contact_id,
            actor_type=ActorType.USER,
            actor_user_id=actor_user_id,
        )
        await self.session.commit()

    async def reset(self, actor_user_id: uuid.UUID) -> int:
        """Delete ALL simulated contacts; their leads/conversations/messages cascade."""
        count = await self.session.scalar(
            select(func.count()).select_from(Contact).where(Contact.is_simulated.is_(True))
        )
        await self.session.execute(delete(Contact).where(Contact.is_simulated.is_(True)))
        record_audit(
            self.session,
            action="simulator.reset",
            entity_type="contact",
            entity_id=None,
            actor_type=ActorType.USER,
            actor_user_id=actor_user_id,
            data={"deleted_contacts": count},
        )
        await self.session.commit()
        return int(count or 0)

    # --- messaging ------------------------------------------------------
    async def send_as_contact(self, contact_id: uuid.UUID, text: str) -> InboundResult:
        contact = await self.get_contact(contact_id)
        inbound = InboundMessage(
            provider=ProviderName.SIMULATED,
            from_phone=contact.phone_number,
            profile_name=contact.display_name,
            provider_message_id=new_simulated_message_id("sim-in"),
            text=text,
            timestamp=datetime.now(UTC),
        )
        return await InboundMessageService(self.session, self.settings, self.queue).handle(inbound)

    async def start_new_conversation(self, contact_id: uuid.UUID) -> Conversation:
        contact = await self.get_contact(contact_id)
        lead, _ = await LeadService(self.session).get_or_create_active(
            contact, source=LeadSource.SIMULATOR
        )
        conversation = await ConversationService(self.session).start_new(
            contact, provider=ProviderName.SIMULATED, lead=lead
        )
        await self.session.commit()
        return conversation

    async def set_message_status(self, message_id: uuid.UUID, status: str) -> Message:
        """Pretend the customer's phone reported delivered/read — via the same
        status handler used for real Meta webhooks."""
        if status not in SIMULATED_STATUSES:
            raise AppError(f"Status harus salah satu dari {sorted(SIMULATED_STATUSES)}")
        message = await self.session.get(Message, message_id)
        if (
            message is None
            or message.provider != ProviderName.SIMULATED
            or message.direction != MessageDirection.OUTBOUND
            or not message.provider_message_id
        ):
            raise NotFoundError("Pesan keluar simulasi tidak ditemukan", code="SIM_MSG_NOT_FOUND")
        await MessageService(self.session).apply_status_update(
            StatusUpdate(
                provider_message_id=message.provider_message_id,
                status=status,
                timestamp=datetime.now(UTC),
                error="Simulated failure" if status == "failed" else None,
            )
        )
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def conversations_for_contact(self, contact_id: uuid.UUID) -> list[Conversation]:
        await self.get_contact(contact_id)
        rows = await self.session.scalars(
            select(Conversation)
            .where(Conversation.contact_id == contact_id)
            .order_by(Conversation.created_at)
        )
        return list(rows)

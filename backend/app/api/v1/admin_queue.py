"""Admin Queue endpoints. Queue items are open conversations with handler=admin_queue."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, require_roles
from app.core.errors import NotFoundError
from app.models import Contact, Conversation, Lead, QualificationState, User
from app.models.enums import ConversationHandler, ConversationStatus, RoleName
from app.services.conversation_control import set_handler

router = APIRouter(prefix="/admin-queue", tags=["admin queue"])
staff = require_roles(RoleName.ADMIN, RoleName.SUPERVISOR)


@router.get("")
async def list_admin_queue(
    _: User = Depends(staff), session: AsyncSession = Depends(get_session)
):
    query = (
        select(Conversation, Contact, Lead, QualificationState)
        .join(Contact, Contact.id == Conversation.contact_id)
        .outerjoin(Lead, Lead.id == Conversation.lead_id)
        .outerjoin(QualificationState, QualificationState.lead_id == Lead.id)
        .where(
            Conversation.status == ConversationStatus.OPEN,
            Conversation.handler == ConversationHandler.ADMIN_QUEUE,
        )
        .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.created_at)
    )
    rows = (await session.execute(query)).all()
    return [
        {
            "conversation_id": str(conversation.id),
            "contact_id": str(contact.id),
            "customer_name": lead.full_name if lead and lead.full_name else contact.display_name,
            "phone_number": contact.phone_number,
            "lead_id": str(lead.id) if lead else None,
            "domicile": lead.domicile_raw if lead else None,
            "vehicle_interest": lead.vehicle_interest if lead else None,
            "temperature": lead.temperature if lead else "cold",
            "lead_status": lead.status if lead else None,
            "source": lead.source if lead else None,
            "is_simulated": contact.is_simulated,
            "handover_reason": state.handover_reason if state else "manual_queue",
            "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
            "unread_count": conversation.unread_count,
        }
        for conversation, contact, lead, state in rows
    ]


@router.post("/{conversation_id}/claim")
async def claim_admin_queue_item(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.role_name not in (RoleName.ADMIN, RoleName.SUPERVISOR):
        from app.core.errors import ForbiddenError
        raise ForbiddenError("Hanya admin atau supervisor yang dapat mengambil antrean")
    conversation = await session.get(Conversation, conversation_id, with_for_update=True)
    if (
        conversation is None
        or conversation.status != ConversationStatus.OPEN
        or conversation.handler != ConversationHandler.ADMIN_QUEUE
    ):
        raise NotFoundError("Item Admin Queue tidak ditemukan atau sudah ditangani", code="QUEUE_ITEM_NOT_FOUND")
    result = await set_handler(session, conversation, ConversationHandler.ADMIN, user)
    result.assigned_user_id = user.id
    await session.commit()
    return {"conversation_id": str(result.id), "handler": result.handler, "assigned_user_id": str(user.id)}

"""Inbox projection with customer and lead fields for the web dashboard."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models import Contact, Conversation, Lead, User
from app.models.enums import ConversationStatus, RoleName

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("")
async def list_inbox(
    handler: str | None = Query(default=None, pattern="^(ai|admin_queue|sales|admin)$"),
    status: str = Query(default="open", pattern="^(open|closed)$"),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(Conversation, Contact, Lead)
        .join(Contact, Contact.id == Conversation.contact_id)
        .outerjoin(Lead, Lead.id == Conversation.lead_id)
        .where(Conversation.status == status)
        .order_by(Conversation.last_message_at.desc().nulls_last())
    )
    if user.role_name == RoleName.SALES:
        query = query.where(Conversation.assigned_user_id == user.id)
    if handler:
        query = query.where(Conversation.handler == handler)
    rows = (await session.execute(query.limit(limit))).all()
    return [
        {
            "id": str(conv.id),
            "contact_id": str(contact.id),
            "lead_id": str(lead.id) if lead else None,
            "customer_name": (lead.full_name if lead and lead.full_name else contact.display_name) or "Customer",
            "phone_number": contact.phone_number,
            "domicile": lead.domicile_raw if lead else None,
            "vehicle_interest": lead.vehicle_interest if lead else None,
            "temperature": lead.temperature if lead else "cold",
            "lead_status": lead.status if lead else None,
            "source": lead.source if lead else None,
            "is_simulated": contact.is_simulated,
            "provider": conv.provider,
            "status": conv.status,
            "handler": conv.handler,
            "assigned_user_id": str(conv.assigned_user_id) if conv.assigned_user_id else None,
            "unread_count": conv.unread_count,
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
        }
        for conv, contact, lead in rows
    ]

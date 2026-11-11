from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_roles
from app.models import Conversation, Lead
from app.models.enums import (
    ConversationHandler,
    ConversationStatus,
    LeadTemperature,
    RoleName,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
staff = require_roles(RoleName.ADMIN, RoleName.SUPERVISOR)


@router.get("/summary")
async def dashboard_summary(
    _: object = Depends(staff), session: AsyncSession = Depends(get_session)
):
    cold = await session.scalar(
        select(func.count(Lead.id)).where(Lead.temperature == LeadTemperature.COLD)
    )
    warm = await session.scalar(
        select(func.count(Lead.id)).where(Lead.temperature == LeadTemperature.WARM)
    )
    open_conversations = await session.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.status == ConversationStatus.OPEN
        )
    )
    queue = await session.scalar(select(func.count(Conversation.id)).where(
        Conversation.status == ConversationStatus.OPEN,
        Conversation.handler == ConversationHandler.ADMIN_QUEUE,
    ))
    sales = await session.scalar(select(func.count(Conversation.id)).where(
        Conversation.status == ConversationStatus.OPEN,
        Conversation.handler == ConversationHandler.SALES,
    ))
    return {
        "cold_leads": cold or 0,
        "warm_leads": warm or 0,
        "open_conversations": open_conversations or 0,
        "admin_queue": queue or 0,
        "assigned_sales_conversations": sales or 0,
    }

"""Humans taking over (or returning) a conversation. The AI stays silent for humans."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Conversation, Lead, QualificationState, User
from app.models.enums import (
    ActorType,
    ConversationHandler,
    HandoverReason,
    QualificationStage,
    RoleName,
)
from app.services.audit_service import record_audit
from app.services.auto_reply_service import hand_over


async def _state_and_lead(session: AsyncSession, conversation: Conversation):
    if conversation.lead_id is None:
        return None, None
    lead = await session.get(Lead, conversation.lead_id)
    state = await session.scalar(
        select(QualificationState).where(QualificationState.lead_id == conversation.lead_id)
    )
    return state, lead


def human_handler_for(user: User) -> str:
    return (
        ConversationHandler.SALES if user.role_name == RoleName.SALES else ConversationHandler.ADMIN
    )


async def take_over(session: AsyncSession, conversation: Conversation, user: User) -> None:
    """Called when a human replies. From now on the AI does not answer."""
    target = human_handler_for(user)
    if conversation.handler == target and conversation.assigned_user_id:
        return
    state, lead = await _state_and_lead(session, conversation)
    await hand_over(
        session,
        conversation,
        state,
        lead,
        HandoverReason.MANUAL_TAKEOVER,
        actor_type=ActorType.USER,
        actor_user_id=user.id,
        to=target,
    )
    conversation.assigned_user_id = conversation.assigned_user_id or user.id


async def set_handler(
    session: AsyncSession, conversation: Conversation, handler: str, user: User
) -> Conversation:
    if handler not in {h.value for h in ConversationHandler}:
        raise AppError("Handler tidak dikenal", code="UNKNOWN_HANDLER")
    state, lead = await _state_and_lead(session, conversation)
    old = conversation.handler
    if handler == ConversationHandler.AI:
        conversation.handler = ConversationHandler.AI
        if state is not None:
            # The AI resumes collecting; already-collected data is kept.
            state.stage = QualificationStage.COLLECTING
            state.handover_reason = None
            state.consecutive_ai_failures = 0
    elif handler in (ConversationHandler.SALES, ConversationHandler.ADMIN):
        await hand_over(
            session,
            conversation,
            state,
            lead,
            HandoverReason.MANUAL_TAKEOVER,
            actor_type=ActorType.USER,
            actor_user_id=user.id,
            to=handler,
        )
        conversation.assigned_user_id = conversation.assigned_user_id or user.id
    else:
        await hand_over(
            session,
            conversation,
            state,
            lead,
            HandoverReason.MANUAL_TAKEOVER,
            actor_type=ActorType.USER,
            actor_user_id=user.id,
            to=handler,
        )
    record_audit(
        session,
        action="conversation.handler_changed",
        entity_type="conversation",
        entity_id=conversation.id,
        actor_type=ActorType.USER,
        actor_user_id=user.id,
        data={"from": old, "to": handler},
    )
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def qualification_view(session: AsyncSession, conversation: Conversation) -> dict:
    state, lead = await _state_and_lead(session, conversation)
    return {
        "conversation_id": conversation.id,
        "handler": conversation.handler,
        "lead_id": lead.id if lead else None,
        "lead_status": lead.status if lead else None,
        "stage": state.stage if state else QualificationStage.COLLECTING,
        "fields": state.fields if state else {},
        "last_asked_field": state.last_asked_field if state else None,
        "handover_reason": state.handover_reason if state else None,
        "history": state.history if state else [],
    }

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ctx, get_current_user, get_session
from app.core.context import AppContext
from app.core.errors import NotFoundError
from app.models import Conversation, User
from app.models.enums import RoleName, SenderType
from app.schemas.messaging import ConversationOut, MessageOut, SendMessageRequest
from app.services.audit_service import record_audit
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _get_visible(session: AsyncSession, user: User, conversation_id: uuid.UUID):
    conversation = await ConversationService(session).get(conversation_id)
    # Sales can only see conversations assigned to them.
    if user.role_name == RoleName.SALES and conversation.assigned_user_id != user.id:
        raise NotFoundError("Percakapan tidak ditemukan", code="CONVERSATION_NOT_FOUND")
    return conversation


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    contact_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
    handler: str | None = Query(default=None, pattern="^(ai|admin_queue|sales)$"),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Conversation]:
    query = select(Conversation).order_by(Conversation.last_message_at.desc().nulls_last())
    if user.role_name == RoleName.SALES:
        query = query.where(Conversation.assigned_user_id == user.id)
    if contact_id:
        query = query.where(Conversation.contact_id == contact_id)
    if status:
        query = query.where(Conversation.status == status)
    if handler:
        query = query.where(Conversation.handler == handler)
    return list(await session.scalars(query.limit(limit)))


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    return await _get_visible(session, user, conversation_id)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _get_visible(session, user, conversation_id)
    return await MessageService(session).list_for_conversation(conversation_id)


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_manual_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    """A human (sales/admin) replies. Goes through the same outgoing message service."""
    conversation = await _get_visible(session, user, conversation_id)
    sender = SenderType.SALES if user.role_name == RoleName.SALES else SenderType.ADMIN
    message = await MessageService(session, ctx.messaging).send_outbound(
        conversation, body.text, sender_type=sender, sender_user_id=user.id
    )
    record_audit(
        session,
        action="message.sent_manual",
        entity_type="message",
        entity_id=message.id,
        actor_type="user",
        actor_user_id=user.id,
    )
    await session.commit()
    return message

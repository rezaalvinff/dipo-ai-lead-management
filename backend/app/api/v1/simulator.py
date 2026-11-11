"""Simulated WhatsApp endpoints. Only mounted when SIMULATOR_ENABLED=true."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ctx, get_session, require_roles
from app.core.context import AppContext
from app.models import User
from app.models.enums import RoleName
from app.schemas.messaging import (
    ContactOut,
    ConversationOut,
    ConversationWithMessages,
    MessageOut,
    SendMessageRequest,
    SimChatOut,
    SimContactCreate,
    SimResetResponse,
    SimSendResponse,
    SimStatusRequest,
)
from app.services.conversation_control import qualification_view
from app.services.message_service import MessageService
from app.services.simulator_service import SimulatorService

router = APIRouter(prefix="/simulator", tags=["simulator"])

simulator_user = require_roles(RoleName.ADMIN, RoleName.SUPERVISOR)


def _service(session: AsyncSession, ctx: AppContext) -> SimulatorService:
    return SimulatorService(session, ctx.settings, ctx.queue)


@router.get("/contacts", response_model=list[ContactOut])
async def list_contacts(
    _: User = Depends(simulator_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    return await _service(session, ctx).list_contacts()


@router.post("/contacts", response_model=ContactOut, status_code=201)
async def create_contact(
    body: SimContactCreate,
    user: User = Depends(simulator_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    return await _service(session, ctx).create_contact(
        body.display_name, body.phone_number, user.id
    )


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: uuid.UUID,
    user: User = Depends(simulator_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _service(session, ctx).delete_contact(contact_id, user.id)


@router.post("/contacts/{contact_id}/messages", response_model=SimSendResponse, status_code=201)
async def send_as_contact(
    contact_id: uuid.UUID,
    body: SendMessageRequest,
    _: User = Depends(simulator_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    result = await _service(session, ctx).send_as_contact(contact_id, body.text)
    return SimSendResponse(
        conversation_id=result.conversation.id,
        lead_id=result.lead.id,
        duplicate=result.duplicate,
        ai_reply_queued=result.ai_reply_queued,
        message=MessageOut.model_validate(result.message) if result.message else None,
    )


@router.post(
    "/contacts/{contact_id}/conversations", response_model=ConversationOut, status_code=201
)
async def start_new_conversation(
    contact_id: uuid.UUID,
    _: User = Depends(simulator_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    return await _service(session, ctx).start_new_conversation(contact_id)


@router.get("/contacts/{contact_id}/chat", response_model=SimChatOut)
async def get_chat(
    contact_id: uuid.UUID,
    _: User = Depends(simulator_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    """Full WhatsApp-like history: every conversation with its messages, oldest first."""
    service = _service(session, ctx)
    contact = await service.get_contact(contact_id)
    conversations = await service.conversations_for_contact(contact_id)
    messages = MessageService(session)
    items = []
    for conv in conversations:
        item = ConversationWithMessages.model_validate(conv)
        item.messages = [
            MessageOut.model_validate(m) for m in await messages.list_for_conversation(conv.id)
        ]
        items.append(item)
    state = await qualification_view(session, conversations[-1]) if conversations else None
    return SimChatOut(contact=ContactOut.model_validate(contact), conversations=items, state=state)


@router.post("/messages/{message_id}/status", response_model=MessageOut)
async def set_message_status(
    message_id: uuid.UUID,
    body: SimStatusRequest,
    _: User = Depends(simulator_user),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    return await _service(session, ctx).set_message_status(message_id, body.status)


@router.post("/reset", response_model=SimResetResponse)
async def reset(
    user: User = Depends(require_roles(RoleName.ADMIN)),
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
):
    return SimResetResponse(deleted_contacts=await _service(session, ctx).reset(user.id))

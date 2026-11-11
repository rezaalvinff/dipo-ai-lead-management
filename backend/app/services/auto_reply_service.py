"""AI agent orchestration for one inbound message (runs in the background worker).

Flow: lock conversation -> skip if a human handles it or a newer message exists
-> build context (state + approved knowledge + history) -> AI proposes ->
backend decides (QualificationService.decide) -> persist state & lead ->
re-check nobody took over meanwhile -> send reply -> hand over if needed.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ai.base import AgentRequest, AIProvider, AIProviderError, AIResult, ChatTurn
from app.adapters.ai.text_match import CITY_ALIASES
from app.adapters.whatsapp.base import MessagingProvider
from app.models import (
    AIInteraction,
    Conversation,
    Lead,
    Message,
    QualificationState,
    Territory,
)
from app.models.enums import (
    ActorType,
    ConversationHandler,
    ConversationStatus,
    FieldStatus,
    HandoverReason,
    LeadStatus,
    MessageDirection,
    QualificationStage,
    SenderType,
)
from app.services.audit_service import record_audit
from app.services.knowledge_service import KnowledgeService
from app.services.message_service import MessageService
from app.services.qualification_service import (
    DecisionInput,
    decide,
    empty_fields,
    known_values,
    missing_fields,
)
from app.services.settings_service import SettingsService, render_template

logger = logging.getLogger(__name__)


async def get_or_create_state(session: AsyncSession, lead: Lead) -> QualificationState:
    state = await session.scalar(
        select(QualificationState).where(QualificationState.lead_id == lead.id)
    )
    if state is None:
        fields = empty_fields()
        # Reuse anything already known about the lead.
        for key, value in (
            ("name", lead.full_name),
            ("domicile", lead.domicile_raw),
            ("vehicle", lead.vehicle_interest),
        ):
            if value:
                fields[key].update(status=FieldStatus.COLLECTED.value, value=value)
        state = QualificationState(
            lead_id=lead.id,
            fields=fields,
            history=[],
            turns=0,
            consecutive_ai_failures=0,
            stage=QualificationStage.COLLECTING,
        )
        session.add(state)
        await session.flush()
    return state


async def hand_over(
    session: AsyncSession,
    conversation: Conversation,
    state: QualificationState | None,
    lead: Lead | None,
    reason: str,
    *,
    actor_type: str = ActorType.SYSTEM,
    actor_user_id: uuid.UUID | None = None,
    to: str = ConversationHandler.ADMIN_QUEUE,
) -> None:
    """Stop the AI for this conversation and pass it to humans."""
    now = datetime.now(UTC)
    conversation.handler = to
    if state is not None:
        state.stage = QualificationStage.HANDED_OVER
        state.handover_reason = reason
        state.handed_over_at = now
        state.last_asked_field = None
    if lead is not None and reason == HandoverReason.QUALIFICATION_COMPLETE:
        lead.status = LeadStatus.QUALIFIED
        lead.qualified_at = lead.qualified_at or now
    record_audit(
        session,
        action="conversation.handover",
        entity_type="conversation",
        entity_id=conversation.id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        data={"reason": reason, "to": to},
    )


class AutoReplyService:
    def __init__(
        self,
        session: AsyncSession,
        ai: AIProvider,
        messaging: MessagingProvider,
        history_limit: int = 30,
    ):
        self.session = session
        self.ai = ai
        self.messages = MessageService(session, messaging)
        self.history_limit = history_limit

    async def reply_to(self, inbound_message_id: uuid.UUID) -> Message | None:
        inbound = await self.session.get(Message, inbound_message_id)
        if inbound is None or inbound.direction != MessageDirection.INBOUND:
            return None
        # One worker at a time per conversation (released at commit/rollback).
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": str(inbound.conversation_id)},
        )
        conversation = await self.session.get(
            Conversation, inbound.conversation_id, populate_existing=True
        )
        if not self._ai_may_reply(conversation):
            logger.info(
                "Skip AI reply: conversation handled by %s", conversation and conversation.handler
            )
            await self.session.commit()
            return None
        if await self._newer_inbound_exists(inbound):
            logger.info("Skip AI reply: a newer customer message will be answered instead")
            await self.session.commit()
            return None

        lead = await self.session.get(Lead, conversation.lead_id) if conversation.lead_id else None
        if lead is None:
            await self.session.commit()
            return None
        state = await get_or_create_state(self.session, lead)
        state.conversation_id = conversation.id
        settings = SettingsService(self.session)

        if not await settings.get("ai.enabled"):
            await hand_over(self.session, conversation, state, lead, HandoverReason.AI_DISABLED)
            await self.session.commit()
            return None
        if state.stage == QualificationStage.HANDED_OVER:
            reply = await settings.get("qualification.returning_customer_message")
            message = await self._send(conversation, reply)
            await hand_over(
                self.session, conversation, state, lead, HandoverReason.RETURNING_CUSTOMER
            )
            await self.session.commit()
            return message

        knowledge_service = KnowledgeService(self.session)
        knowledge = await knowledge_service.build_context(state.fields["vehicle"].get("value"))
        city_catalog = await self._city_catalog()
        is_first_reply = not await self._has_outbound(conversation)
        request = AgentRequest(
            history=await self._history(conversation),
            known=known_values(state.fields),
            field_status={k: v["status"] for k, v in state.fields.items()},
            missing_fields=missing_fields(state.fields),
            last_asked_field=state.last_asked_field,
            is_first_reply=is_first_reply,
            knowledge=knowledge,
            city_catalog=city_catalog,
        )

        result: AIResult | None = None
        error: AIProviderError | None = None
        try:
            result = await self.ai.run_turn(request)
        except AIProviderError as exc:
            error = exc
            logger.warning("AI provider failed: %s", exc)

        decision = decide(
            DecisionInput(
                fields=state.fields,
                output=result.output if result else None,
                knowledge=knowledge,
                city_catalog=city_catalog,
                max_asks=await settings.get("qualification.max_asks_per_field"),
                is_first_reply=is_first_reply,
                consecutive_ai_failures=state.consecutive_ai_failures,
                messages={
                    "closing": await settings.get("qualification.closing_message"),
                    "human": await settings.get("qualification.human_handover_message"),
                    "ai_unavailable": await settings.get("qualification.ai_unavailable_message"),
                },
            )
        )

        # --- persist state & lead (backend-validated values only) ---
        state.fields = decision.fields
        state.history = [*state.history, *decision.changes]
        state.turns += 1
        state.consecutive_ai_failures = 0 if result else state.consecutive_ai_failures + 1
        state.last_asked_field = decision.asked_field if not decision.handover_reason else None
        await self._sync_lead(lead, decision.fields, knowledge_service)
        for change in decision.changes:
            record_audit(
                self.session,
                action=f"lead.field_{change['type']}",
                entity_type="lead",
                entity_id=lead.id,
                actor_type=ActorType.AI,
                data={"field": change["field"], "old": change["old"], "new": change["new"]},
            )
        self.session.add(
            AIInteraction(
                conversation_id=conversation.id,
                message_id=inbound.id,
                provider=getattr(self.ai, "name", "unknown"),
                model=result.model if result else getattr(self.ai, "model", "unknown"),
                status="ok" if result else (error.status if error else "error"),
                ai_output=result.output.model_dump() if result else None,
                decision=decision.as_log(),
                input_tokens=result.input_tokens if result else None,
                output_tokens=result.output_tokens if result else None,
                latency_ms=result.latency_ms if result else None,
                error=str(error) if error else None,
            )
        )

        # --- a human may have taken over while the AI was thinking ---
        await self.session.refresh(conversation, with_for_update=True)
        if not self._ai_may_reply(conversation):
            logger.info("Human took over during AI generation; reply discarded")
            await self.session.commit()
            return None

        values = {
            "nama": decision.fields["name"]["value"],
            "domisili": decision.fields["domicile"]["value"],
            "unit": decision.fields["vehicle"]["value"],
        }
        reply_text = (
            render_template(decision.reply or "", values)
            if decision.reply_source in ("closing", "human_handover", "ai_unavailable")
            else decision.reply
        )
        message = await self._send(conversation, reply_text) if reply_text else None
        if decision.handover_reason:
            await hand_over(self.session, conversation, state, lead, decision.handover_reason)
        await self.session.commit()
        return message

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _ai_may_reply(conversation: Conversation | None) -> bool:
        return (
            conversation is not None
            and conversation.status == ConversationStatus.OPEN
            and conversation.handler == ConversationHandler.AI
        )

    async def _newer_inbound_exists(self, inbound: Message) -> bool:
        newer = await self.session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == inbound.conversation_id,
                Message.direction == MessageDirection.INBOUND,
                Message.created_at > inbound.created_at,
            )
        )
        return bool(newer)

    async def _has_outbound(self, conversation: Conversation) -> bool:
        return bool(
            await self.session.scalar(
                select(Message.id)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.direction == MessageDirection.OUTBOUND,
                )
                .limit(1)
            )
        )

    async def _history(self, conversation: Conversation) -> list[ChatTurn]:
        rows = await self.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(self.history_limit)
        )
        return [
            ChatTurn(
                role="contact" if m.direction == MessageDirection.INBOUND else "assistant",
                text=m.content,
            )
            for m in reversed(list(rows))
        ]

    async def _city_catalog(self) -> dict[str, list[str]]:
        catalog = {name: list(aliases) for name, aliases in CITY_ALIASES.items()}
        for territory in await self.session.scalars(
            select(Territory).where(Territory.is_active.is_(True))
        ):
            catalog.setdefault(territory.name, [])
            catalog[territory.name] = sorted({*catalog[territory.name], *(territory.aliases or [])})
        return catalog

    async def _sync_lead(self, lead: Lead, fields: dict, knowledge: KnowledgeService) -> None:
        lead.full_name = fields["name"]["value"]
        lead.domicile_raw = fields["domicile"]["value"]
        lead.vehicle_interest = fields["vehicle"]["value"]
        model_ids = await knowledge.vehicle_model_ids()
        lead.vehicle_model_id = model_ids.get(lead.vehicle_interest or "")
        lead.territory_id = None
        if lead.domicile_raw:
            for territory in await self.session.scalars(
                select(Territory).where(Territory.is_active.is_(True))
            ):
                names = {territory.name.lower(), *(a.lower() for a in territory.aliases or [])}
                if lead.domicile_raw.lower() in names:
                    lead.territory_id = territory.id
                    break
        if lead.status == LeadStatus.NEW and any(f["value"] for f in fields.values()):
            lead.status = LeadStatus.QUALIFYING

    async def _send(self, conversation: Conversation, text_: str) -> Message:
        return await self.messages.send_outbound(conversation, text_, sender_type=SenderType.AI)

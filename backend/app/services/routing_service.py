"""Automatic territory matching and safe lead assignment.

A lead becomes WARM only after an actual active sales assignment is persisted.
Unknown/unmapped territories and unavailable/full agents remain COLD in Admin Queue.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models import AgentProfile, Assignment, Conversation, Lead, Territory, TerritoryMapping, User
from app.models.enums import ConversationHandler, LeadStatus, LeadTemperature
from app.services.audit_service import record_audit


def normalize_area(value: str) -> str:
    return " ".join(value.casefold().replace(".", " ").replace(",", " ").split())


class RoutingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _match_territory(self, domicile: str) -> Territory | None:
        normalized = normalize_area(domicile)
        territories = await self.session.scalars(
            select(Territory).where(Territory.is_active.is_(True)).order_by(Territory.name)
        )
        matches = [
            territory
            for territory in territories
            if normalized
            in {normalize_area(territory.name), *(normalize_area(a) for a in (territory.aliases or []))}
        ]
        # An ambiguous alias is deliberately not guessed.
        return matches[0] if len(matches) == 1 else None

    async def route_qualified_lead(
        self, lead: Lead, conversation: Conversation, *, actor_user_id: uuid.UUID | None = None
    ) -> dict:
        """Route only fully-qualified leads. Safe to call repeatedly."""
        if not all((lead.full_name, lead.domicile_raw, lead.vehicle_interest)):
            lead.temperature = LeadTemperature.COLD
            return {"assigned": False, "reason": "qualification_incomplete"}

        # Serialize routing for the same lead and refresh the persisted state.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"lead-routing:{lead.id}"},
        )
        await self.session.refresh(lead)
        await self.session.refresh(conversation)

        if lead.assigned_agent_id:
            profile = await self.session.get(AgentProfile, lead.assigned_agent_id)
            if profile:
                conversation.handler = ConversationHandler.SALES
                conversation.assigned_user_id = profile.user_id
                lead.temperature = LeadTemperature.WARM
                return {"assigned": True, "agent_profile_id": str(profile.id), "assigned_user_id": str(profile.user_id), "reason": "already_assigned"}

        territory = await self._match_territory(lead.domicile_raw)
        if territory is None:
            lead.territory_id = None
            return await self._send_to_admin_queue(lead, conversation, "territory_unmapped")
        lead.territory_id = territory.id

        mappings = list(
            await self.session.scalars(
                select(TerritoryMapping)
                .where(TerritoryMapping.territory_id == territory.id)
                .order_by(TerritoryMapping.priority.asc(), TerritoryMapping.created_at.asc())
            )
        )
        if not mappings:
            return await self._send_to_admin_queue(lead, conversation, "territory_without_mapping")

        candidates: list[AgentProfile] = []
        for mapping in mappings:
            profile = await self.session.scalar(
                select(AgentProfile)
                .join(User, User.id == AgentProfile.user_id)
                .where(
                    AgentProfile.id == mapping.agent_profile_id,
                    AgentProfile.is_available.is_(True),
                    User.is_active.is_(True),
                )
            )
            if profile is None:
                continue
            active_count = await self.session.scalar(
                select(func.count(Lead.id)).where(
                    Lead.assigned_agent_id == profile.id,
                    Lead.status.not_in((LeadStatus.WON, LeadStatus.LOST)),
                )
            )
            if profile.max_active_leads is not None and active_count >= profile.max_active_leads:
                continue
            candidates.append(profile)

        if not candidates:
            return await self._send_to_admin_queue(lead, conversation, "no_available_agent")

        # Round-robin: select the eligible agent assigned least recently.
        candidates.sort(key=lambda p: (p.last_assigned_at is not None, p.last_assigned_at or p.created_at, str(p.id)))
        agent = candidates[0]
        now = datetime.now(UTC)
        await self._persist_assignment(
            lead, conversation, agent, reason=f"territory_match:{territory.name}",
            assigned_by_type="system", assigned_by_user_id=actor_user_id, now=now,
        )
        return {
            "assigned": True,
            "territory": territory.name,
            "agent_profile_id": str(agent.id),
            "assigned_user_id": str(agent.user_id),
            "reason": "territory_match",
        }

    async def _send_to_admin_queue(self, lead: Lead, conversation: Conversation, reason: str) -> dict:
        lead.temperature = LeadTemperature.COLD
        lead.status = LeadStatus.QUALIFIED
        lead.assigned_agent_id = None
        conversation.handler = ConversationHandler.ADMIN_QUEUE
        conversation.assigned_user_id = None
        record_audit(
            self.session, action="lead.routing_queued", entity_type="lead", entity_id=lead.id,
            data={"reason": reason, "domicile": lead.domicile_raw},
        )
        return {"assigned": False, "reason": reason, "queue": "admin_queue"}

    async def _persist_assignment(
        self, lead: Lead, conversation: Conversation, agent: AgentProfile, *,
        reason: str, assigned_by_type: str, assigned_by_user_id: uuid.UUID | None,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(UTC)
        previous = await self.session.scalars(
            select(Assignment).where(Assignment.lead_id == lead.id, Assignment.ended_at.is_(None))
        )
        for assignment in previous:
            assignment.ended_at = now
        self.session.add(Assignment(
            lead_id=lead.id, agent_profile_id=agent.id, assigned_by_type=assigned_by_type,
            assigned_by_user_id=assigned_by_user_id, reason=reason,
        ))
        agent.last_assigned_at = now
        lead.assigned_agent_id = agent.id
        lead.temperature = LeadTemperature.WARM
        lead.status = LeadStatus.ASSIGNED
        conversation.handler = ConversationHandler.SALES
        conversation.assigned_user_id = agent.user_id
        record_audit(
            self.session, action="lead.assigned", entity_type="lead", entity_id=lead.id,
            actor_type="system" if assigned_by_type == "system" else "user",
            actor_user_id=assigned_by_user_id,
            data={"agent_profile_id": str(agent.id), "reason": reason, "temperature": "warm"},
        )

    async def manual_assign(
        self, lead_id: uuid.UUID, agent_profile_id: uuid.UUID, actor: User
    ) -> Lead:
        lead = await self.session.get(Lead, lead_id, with_for_update=True)
        if lead is None:
            raise NotFoundError("Lead tidak ditemukan", code="LEAD_NOT_FOUND")
        if not all((lead.full_name, lead.domicile_raw, lead.vehicle_interest)):
            raise AppError("Lead belum memiliki nama, domisili, dan unit lengkap", code="LEAD_NOT_QUALIFIED")
        agent = await self.session.scalar(
            select(AgentProfile).join(User, User.id == AgentProfile.user_id).where(
                AgentProfile.id == agent_profile_id, AgentProfile.is_available.is_(True), User.is_active.is_(True)
            )
        )
        if agent is None:
            raise NotFoundError("Sales tidak ditemukan atau sedang tidak tersedia", code="AGENT_NOT_AVAILABLE")
        conversation = await self.session.scalar(
            select(Conversation).where(Conversation.lead_id == lead.id, Conversation.status == "open")
            .order_by(Conversation.created_at.desc()).limit(1)
        )
        if conversation is None:
            raise NotFoundError("Percakapan aktif untuk lead ini tidak ditemukan", code="CONVERSATION_NOT_FOUND")
        await self._persist_assignment(
            lead, conversation, agent, reason="manual_admin_assignment",
            assigned_by_type="user", assigned_by_user_id=actor.id,
        )
        record_audit(
            self.session, action="lead.manual_assigned", entity_type="lead", entity_id=lead.id,
            actor_type="user", actor_user_id=actor.id,
            data={"agent_profile_id": str(agent.id)},
        )
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

import pytest
from sqlalchemy import select

from app.models import (
    AgentProfile,
    Contact,
    Conversation,
    Lead,
    Territory,
    TerritoryMapping,
    User,
)
from app.models.enums import ConversationHandler, LeadStatus, LeadTemperature
from app.services.routing_service import RoutingService


async def _make_lead(session, *, domicile="Medan", complete=True):
    contact = Contact(
        phone_number="+6280000000123",
        display_name="Customer Dummy",
        is_simulated=True,
    )
    session.add(contact)
    await session.flush()
    lead = Lead(
        contact_id=contact.id,
        full_name="Andi Dummy" if complete else None,
        domicile_raw=domicile if complete else None,
        vehicle_interest="Xpander" if complete else None,
        temperature=LeadTemperature.COLD,
        status=LeadStatus.QUALIFIED if complete else LeadStatus.QUALIFYING,
        is_simulated=True,
    )
    session.add(lead)
    await session.flush()
    conversation = Conversation(
        contact_id=contact.id, lead_id=lead.id, provider="simulated",
        status="open", handler=ConversationHandler.ADMIN_QUEUE,
    )
    session.add(conversation)
    await session.flush()
    return lead, conversation


@pytest.mark.asyncio
async def test_qualified_lead_routes_to_mapped_agent_and_becomes_warm(app, users):
    async with app.state.ctx.session_factory() as session:
        agent_user = await session.scalar(select(User).where(User.email == users["sales"]))
        agent = await session.scalar(
            select(AgentProfile).where(AgentProfile.user_id == agent_user.id)
        )
        territory = Territory(name="Medan", aliases=["medan kota"], is_active=True)
        session.add(territory)
        await session.flush()
        session.add(
            TerritoryMapping(
                territory_id=territory.id,
                agent_profile_id=agent.id,
                priority=1,
            )
        )
        lead, conversation = await _make_lead(session)
        await session.flush()

        result = await RoutingService(session).route_qualified_lead(lead, conversation)
        await session.commit()

        assert result["assigned"] is True
        assert lead.temperature == LeadTemperature.WARM
        assert lead.assigned_agent_id == agent.id
        assert lead.territory_id == territory.id
        assert conversation.handler == ConversationHandler.SALES
        assert conversation.assigned_user_id == agent_user.id


@pytest.mark.asyncio
async def test_unmapped_domicile_stays_cold_and_goes_to_admin_queue(app):
    async with app.state.ctx.session_factory() as session:
        lead, conversation = await _make_lead(session, domicile="Binjai")
        result = await RoutingService(session).route_qualified_lead(lead, conversation)
        await session.commit()

        assert result["assigned"] is False
        assert result["reason"] == "territory_unmapped"
        assert lead.temperature == LeadTemperature.COLD
        assert lead.assigned_agent_id is None
        assert conversation.handler == ConversationHandler.ADMIN_QUEUE


@pytest.mark.asyncio
async def test_incomplete_lead_cannot_become_warm_or_assigned(app):
    async with app.state.ctx.session_factory() as session:
        lead, conversation = await _make_lead(session, complete=False)
        result = await RoutingService(session).route_qualified_lead(lead, conversation)
        await session.commit()

        assert result["assigned"] is False
        assert result["reason"] == "qualification_incomplete"
        assert lead.temperature == LeadTemperature.COLD
        assert lead.assigned_agent_id is None

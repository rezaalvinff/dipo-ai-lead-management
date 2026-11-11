"""Lead routing, territory master data and manual assignment."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_roles
from app.core.errors import ConflictError, NotFoundError
from app.models import (
    AgentProfile,
    Assignment,
    Lead,
    Territory,
    TerritoryMapping,
    User,
)
from app.models.enums import RoleName
from app.schemas.routing import (
    ManualAssignRequest, TerritoryCreate, TerritoryMappingCreate, TerritoryMappingOut,
    TerritoryMappingUpdate, TerritoryOut, TerritoryUpdate,
)
from app.services.audit_service import record_audit
from app.services.routing_service import RoutingService

router = APIRouter(prefix="", tags=["leads & routing"])
admin = require_roles(RoleName.ADMIN)
staff = require_roles(RoleName.ADMIN, RoleName.SUPERVISOR)


@router.get("/leads")
async def list_leads(
    temperature: str | None = Query(default=None, pattern="^(cold|warm)$"),
    status: str | None = None,
    domicile: str | None = None,
    agent_profile_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
):
    query = select(Lead).order_by(Lead.created_at.desc())
    if temperature:
        query = query.where(Lead.temperature == temperature)
    if status:
        query = query.where(Lead.status == status)
    if domicile:
        query = query.where(Lead.domicile_raw.ilike(f"%{domicile}%"))
    if agent_profile_id:
        query = query.where(Lead.assigned_agent_id == agent_profile_id)
    rows = list(await session.scalars(query.limit(limit)))
    return [{
        "id": str(x.id), "full_name": x.full_name, "domicile": x.domicile_raw,
        "vehicle_interest": x.vehicle_interest, "temperature": x.temperature,
        "status": x.status, "source": x.source,
        "assigned_agent_id": str(x.assigned_agent_id) if x.assigned_agent_id else None,
        "territory_id": str(x.territory_id) if x.territory_id else None,
        "is_simulated": x.is_simulated, "created_at": x.created_at.isoformat(),
    } for x in rows]


@router.get("/leads/{lead_id}/assignments")
async def lead_assignments(
    lead_id: uuid.UUID, _: User = Depends(staff), session: AsyncSession = Depends(get_session)
):
    if await session.get(Lead, lead_id) is None:
        raise NotFoundError("Lead tidak ditemukan", code="LEAD_NOT_FOUND")
    rows = await session.scalars(
        select(Assignment).where(Assignment.lead_id == lead_id).order_by(Assignment.created_at.desc())
    )
    return [{
        "id": str(x.id), "agent_profile_id": str(x.agent_profile_id),
        "assigned_by_type": x.assigned_by_type, "assigned_by_user_id": str(x.assigned_by_user_id) if x.assigned_by_user_id else None,
        "reason": x.reason, "created_at": x.created_at.isoformat(),
        "ended_at": x.ended_at.isoformat() if x.ended_at else None,
    } for x in rows]


@router.post("/leads/{lead_id}/assign")
async def assign_lead(
    lead_id: uuid.UUID, body: ManualAssignRequest, user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    lead = await RoutingService(session).manual_assign(lead_id, body.agent_profile_id, user)
    return {"id": str(lead.id), "temperature": lead.temperature, "status": lead.status,
            "assigned_agent_id": str(lead.assigned_agent_id)}


@router.get("/territories", response_model=list[TerritoryOut])
async def list_territories(_: User = Depends(staff), session: AsyncSession = Depends(get_session)):
    return list(await session.scalars(select(Territory).order_by(Territory.name)))


@router.post("/territories", response_model=TerritoryOut, status_code=201)
async def create_territory(
    body: TerritoryCreate, user: User = Depends(admin), session: AsyncSession = Depends(get_session)
):
    exists = await session.scalar(select(Territory.id).where(Territory.name.ilike(body.name)))
    if exists:
        raise ConflictError("Wilayah sudah terdaftar", code="TERRITORY_EXISTS")
    item = Territory(**body.model_dump())
    session.add(item)
    record_audit(session, action="territory.created", entity_type="territory", entity_id=item.id,
                 actor_type="user", actor_user_id=user.id)
    await session.commit()
    await session.refresh(item)
    return item


@router.patch("/territories/{territory_id}", response_model=TerritoryOut)
async def update_territory(
    territory_id: uuid.UUID, body: TerritoryUpdate, user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Territory, territory_id)
    if item is None:
        raise NotFoundError("Wilayah tidak ditemukan", code="TERRITORY_NOT_FOUND")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    record_audit(session, action="territory.updated", entity_type="territory", entity_id=item.id,
                 actor_type="user", actor_user_id=user.id)
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/territory-mappings", response_model=TerritoryMappingOut, status_code=201)
async def create_mapping(
    body: TerritoryMappingCreate, user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    if await session.get(Territory, body.territory_id) is None:
        raise NotFoundError("Wilayah tidak ditemukan", code="TERRITORY_NOT_FOUND")
    if await session.get(AgentProfile, body.agent_profile_id) is None:
        raise NotFoundError("Profil sales tidak ditemukan", code="AGENT_NOT_FOUND")
    exists = await session.scalar(select(TerritoryMapping.id).where(
        TerritoryMapping.territory_id == body.territory_id,
        TerritoryMapping.agent_profile_id == body.agent_profile_id,
    ))
    if exists:
        raise ConflictError("Pemetaan wilayah dan sales sudah ada", code="MAPPING_EXISTS")
    item = TerritoryMapping(**body.model_dump())
    session.add(item)
    record_audit(session, action="territory_mapping.created", entity_type="territory_mapping",
                 entity_id=item.id, actor_type="user", actor_user_id=user.id)
    await session.commit()
    await session.refresh(item)
    return item


@router.patch("/territory-mappings/{mapping_id}", response_model=TerritoryMappingOut)
async def update_mapping(
    mapping_id: uuid.UUID, body: TerritoryMappingUpdate, user: User = Depends(admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(TerritoryMapping, mapping_id)
    if item is None:
        raise NotFoundError("Pemetaan wilayah tidak ditemukan", code="MAPPING_NOT_FOUND")
    item.priority = body.priority
    record_audit(session, action="territory_mapping.updated", entity_type="territory_mapping",
                 entity_id=item.id, actor_type="user", actor_user_id=user.id)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/territory-mappings/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: uuid.UUID, user: User = Depends(admin), session: AsyncSession = Depends(get_session)
):
    item = await session.get(TerritoryMapping, mapping_id)
    if item is None:
        raise NotFoundError("Pemetaan wilayah tidak ditemukan", code="MAPPING_NOT_FOUND")
    record_audit(session, action="territory_mapping.deleted", entity_type="territory_mapping",
                 entity_id=item.id, actor_type="user", actor_user_id=user.id)
    await session.delete(item)
    await session.commit()


@router.get("/agents")
async def list_agents(
    active_only: bool = True,
    _: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
):
    """List sales profiles and current active workload for assignment UI."""
    query = select(AgentProfile, User).join(User, User.id == AgentProfile.user_id)
    if active_only:
        query = query.where(AgentProfile.is_available.is_(True), User.is_active.is_(True))
    rows = (await session.execute(query.order_by(AgentProfile.display_name))).all()
    result = []
    for profile, user in rows:
        active_count = await session.scalar(
            select(func.count(Lead.id)).where(
                Lead.assigned_agent_id == profile.id,
                Lead.status.not_in(("won", "lost")),
            )
        )
        result.append({
            "id": str(profile.id),
            "user_id": str(user.id),
            "display_name": profile.display_name,
            "phone_number": profile.phone_number,
            "is_available": profile.is_available,
            "user_is_active": user.is_active,
            "max_active_leads": profile.max_active_leads,
            "active_leads": active_count or 0,
        })
    return result

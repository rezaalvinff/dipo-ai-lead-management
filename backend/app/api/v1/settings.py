from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_roles
from app.models import User
from app.models.enums import RoleName
from app.schemas.knowledge import SettingOut, SettingUpdate
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


async def _one(service: SettingsService, key: str) -> SettingOut:
    return next(SettingOut(**s) for s in await service.list_all() if s["key"] == key)


@router.get("", response_model=list[SettingOut])
async def list_settings(
    _: User = Depends(require_roles(RoleName.ADMIN, RoleName.SUPERVISOR)),
    session: AsyncSession = Depends(get_session),
):
    return await SettingsService(session).list_all()


@router.put("/{key}", response_model=SettingOut)
async def update_setting(
    key: str,
    body: SettingUpdate,
    user: User = Depends(require_roles(RoleName.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    service = SettingsService(session)
    await service.set(key, body.value, user.id)
    return await _one(service, key)


@router.delete("/{key}", response_model=SettingOut)
async def reset_setting(
    key: str,
    user: User = Depends(require_roles(RoleName.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    service = SettingsService(session)
    await service.reset(key, user.id)
    return await _one(service, key)

import uuid
from collections.abc import AsyncIterator, Callable

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AppContext
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models import User

ACCESS_COOKIE = "access_token"


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_session(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[AsyncSession]:
    async with ctx.session_factory() as session:
        yield session


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


async def get_current_user(
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = _extract_token(request)
    if not token:
        raise UnauthorizedError("Silakan login terlebih dahulu")
    try:
        payload = decode_access_token(ctx.settings, token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise UnauthorizedError("Sesi tidak valid atau kedaluwarsa", code="INVALID_TOKEN") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Akun tidak aktif", code="INACTIVE_USER")
    return user


def require_roles(*roles: str) -> Callable:
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role_name not in roles:
            raise ForbiddenError("Anda tidak memiliki akses ke fitur ini")
        return user

    return checker

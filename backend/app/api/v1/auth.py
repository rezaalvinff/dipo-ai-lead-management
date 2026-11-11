from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ACCESS_COOKIE, get_ctx, get_current_user, get_session, require_roles
from app.core.context import AppContext
from app.models import User
from app.models.enums import RoleName
from app.schemas.auth import LoginRequest, LoginResponse, UserCreate, UserOut
from app.services.auth_service import AuthService, UserService

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    ctx: AppContext = Depends(get_ctx),
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    user, token = await AuthService(session, ctx.settings).login(body.email, body.password)
    response.set_cookie(
        ACCESS_COOKIE,
        token,
        httponly=True,
        secure=ctx.settings.cookie_secure,
        samesite="lax",
        max_age=ctx.settings.jwt_expire_minutes * 60,
    )
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/auth/logout", status_code=204)
async def logout(response: Response) -> Response:
    response.delete_cookie(ACCESS_COOKIE)
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/users", response_model=list[UserOut], tags=["users"])
async def list_users(
    _: User = Depends(require_roles(RoleName.ADMIN, RoleName.SUPERVISOR)),
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    return await UserService(session).list_users()


@router.post("/users", response_model=UserOut, status_code=201, tags=["users"])
async def create_user(
    body: UserCreate,
    admin: User = Depends(require_roles(RoleName.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> User:
    return await UserService(session).create_user(
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role=body.role,
        actor_user_id=admin.id,
        agent_phone=body.agent_phone,
    )

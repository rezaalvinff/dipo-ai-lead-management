import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AgentProfile, Role, User
from app.models.enums import ActorType, RoleName
from app.services.audit_service import record_audit

MIN_PASSWORD_LENGTH = 8


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings

    async def login(self, email: str, password: str) -> tuple[User, str]:
        user = await self.session.scalar(select(User).where(User.email == email.lower()))
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Email atau password salah", code="INVALID_CREDENTIALS")
        user.last_login_at = datetime.now(UTC)
        record_audit(
            self.session,
            action="auth.login",
            entity_type="user",
            entity_id=user.id,
            actor_type=ActorType.USER,
            actor_user_id=user.id,
        )
        await self.session.commit()
        return user, create_access_token(self.settings, user.id, user.role_name)


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_users(self) -> list[User]:
        return list(await self.session.scalars(select(User).order_by(User.created_at)))

    async def get_role(self, name: str) -> Role:
        role = await self.session.scalar(select(Role).where(Role.name == name))
        if role is None:
            raise AppError(f"Role '{name}' tidak dikenal", code="UNKNOWN_ROLE")
        return role

    async def create_user(
        self,
        *,
        email: str,
        full_name: str,
        password: str,
        role: str,
        actor_user_id: uuid.UUID | None = None,
        agent_phone: str | None = None,
    ) -> User:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AppError(f"Password minimal {MIN_PASSWORD_LENGTH} karakter", code="WEAK_PASSWORD")
        role_obj = await self.get_role(role)
        user = User(
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password),
            role_id=role_obj.id,
            is_active=True,
        )
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Email sudah terdaftar", code="EMAIL_TAKEN") from exc
        if role == RoleName.SALES:
            self.session.add(
                AgentProfile(user_id=user.id, display_name=full_name, phone_number=agent_phone)
            )
        record_audit(
            self.session,
            action="user.created",
            entity_type="user",
            entity_id=user.id,
            actor_type=ActorType.USER if actor_user_id else ActorType.SYSTEM,
            actor_user_id=actor_user_id,
            data={"role": role},
        )
        await self.session.commit()
        await self.session.refresh(user)
        return user

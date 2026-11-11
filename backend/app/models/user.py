import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """admin / supervisor / sales. Seeded by the initial migration."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(30), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person who logs in to the dashboard."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[Role] = relationship(lazy="joined")
    agent_profile: Mapped["AgentProfile | None"] = relationship(
        back_populates="user", uselist=False
    )

    @property
    def role_name(self) -> str:
        return self.role.name


class AgentProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Sales-specific data for a user who can receive leads."""

    __tablename__ = "agent_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    display_name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str | None] = mapped_column(String(20))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    max_active_leads: Mapped[int | None] = mapped_column(Integer)
    last_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="agent_profile")

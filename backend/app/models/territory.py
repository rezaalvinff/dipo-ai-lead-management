import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Territory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A domicile area used for routing, e.g. "Jakarta Selatan"."""

    __tablename__ = "territories"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TerritoryMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Which sales agent serves which territory (many-to-many with priority)."""

    __tablename__ = "territory_mappings"
    __table_args__ = (UniqueConstraint("territory_id", "agent_profile_id"),)

    territory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("territories.id", ondelete="CASCADE")
    )
    agent_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE")
    )
    priority: Mapped[int] = mapped_column(Integer, default=100)

    territory: Mapped[Territory] = relationship()

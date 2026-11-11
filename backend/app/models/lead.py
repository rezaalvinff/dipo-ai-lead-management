import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.contact import Contact
from app.models.enums import LeadSource, LeadStatus, LeadTemperature


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    # Data collected by the AI (raw answer + matched reference).
    full_name: Mapped[str | None] = mapped_column(String(120))
    domicile_raw: Mapped[str | None] = mapped_column(String(150))
    territory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("territories.id", ondelete="SET NULL")
    )
    vehicle_interest: Mapped[str | None] = mapped_column(String(150))
    vehicle_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicle_models.id", ondelete="SET NULL")
    )

    temperature: Mapped[str] = mapped_column(String(10), default=LeadTemperature.COLD)
    status: Mapped[str] = mapped_column(String(20), default=LeadStatus.NEW, index=True)
    source: Mapped[str] = mapped_column(String(20), default=LeadSource.WHATSAPP)
    ad_referral: Mapped[dict | None] = mapped_column(JSONB)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"), index=True
    )
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    contact: Mapped[Contact] = relationship()


class Assignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """History of which sales agent held a lead and why."""

    __tablename__ = "assignments"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    agent_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE")
    )
    assigned_by_type: Mapped[str] = mapped_column(String(10))  # system | user
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConversionEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Events reported to ad platforms. In development they are only recorded."""

    __tablename__ = "conversion_events"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    event_name: Mapped[str] = mapped_column(String(40))  # Lead | QualifiedLead | ...
    provider: Mapped[str] = mapped_column(String(20))  # noop | meta_capi
    status: Mapped[str] = mapped_column(String(15))  # pending | sent | skipped_dev | failed
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Who did what, when. No FK to entities so history survives deletes."""

    __tablename__ = "audit_logs"

    actor_type: Mapped[str] = mapped_column(String(10))  # user | system | ai | contact
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)


class WebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Raw webhook deliveries. Unique event_key = duplicate webhook protection."""

    __tablename__ = "webhook_events"

    source: Mapped[str] = mapped_column(String(20))
    event_key: Mapped[str] = mapped_column(String(128), unique=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

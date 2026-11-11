"""Knowledge base: the ONLY information the AI may use when answering customers.

Every item has an approval status. The AI only sees items that are
``approved``, active, and (for time-limited info like promos) currently valid.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import KnowledgeStatus


class ApprovalMixin:
    status: Mapped[str] = mapped_column(String(15), default=KnowledgeStatus.DRAFT, index=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VehicleModel(UUIDPrimaryKeyMixin, TimestampMixin, ApprovalMixin, Base):
    """A Mitsubishi model, e.g. "Xpander". Aliases help match typos/informal names."""

    __tablename__ = "vehicle_models"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    category: Mapped[str] = mapped_column(String(50), default="passenger")  # passenger | commercial
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    variants: Mapped[list["VehicleVariant"]] = relationship(
        back_populates="vehicle_model",
        cascade="all, delete-orphan",
        order_by="VehicleVariant.sort_order",
    )


class VehicleVariant(UUIDPrimaryKeyMixin, TimestampMixin, ApprovalMixin, Base):
    """A variant/trim with its specs and (approved) price."""

    __tablename__ = "vehicle_variants"

    vehicle_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicle_models.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    transmission: Mapped[str | None] = mapped_column(String(30))
    fuel_type: Mapped[str | None] = mapped_column(String(30))
    specs: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"Mesin": "1.5L", "Kursi": "7"}
    price_otr: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))
    price_note: Mapped[str | None] = mapped_column(String(200))  # e.g. "OTR Medan, Nov 2026"
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    vehicle_model: Mapped[VehicleModel] = relationship(back_populates="variants")


class KnowledgeBaseArticle(UUIDPrimaryKeyMixin, TimestampMixin, ApprovalMixin, Base):
    """Free-text knowledge: promo, DP, angsuran, FAQ, dealer info, policy, spec notes."""

    __tablename__ = "knowledge_base_articles"

    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), index=True)  # see KnowledgeCategory
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    vehicle_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicle_models.id", ondelete="SET NULL"), index=True
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

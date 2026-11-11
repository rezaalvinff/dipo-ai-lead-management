from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Marketing campaign a lead came from (e.g. a Click-to-WhatsApp ad)."""

    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(150))
    platform: Mapped[str] = mapped_column(String(30), default="meta")  # meta | google | offline
    external_campaign_id: Mapped[str | None] = mapped_column(String(64), index=True)
    external_adset_id: Mapped[str | None] = mapped_column(String(64))
    external_ad_id: Mapped[str | None] = mapped_column(String(64), index=True)
    utm: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

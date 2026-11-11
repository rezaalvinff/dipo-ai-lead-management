from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A WhatsApp user (customer) who chats with the business."""

    __tablename__ = "contacts"

    phone_number: Mapped[str] = mapped_column(String(20), unique=True)  # E.164
    wa_id: Mapped[str | None] = mapped_column(String(32))
    display_name: Mapped[str | None] = mapped_column(String(120))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)

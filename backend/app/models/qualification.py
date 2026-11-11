"""Conversation state: what the AI has collected for a lead, decided by the BACKEND."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import QualificationStage


class QualificationState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One per lead, so a returning customer is never asked the same thing twice.

    ``fields`` looks like::

        {"name":     {"status": "collected", "value": "Andi", "asks": 1},
         "domicile": {"status": "missing",   "value": null,   "asks": 1},
         "vehicle":  {"status": "declined",  "value": null,   "asks": 2}}

    ``history`` is an append-only list of changes (incl. customer corrections).
    """

    __tablename__ = "qualification_states"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), unique=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    stage: Mapped[str] = mapped_column(String(20), default=QualificationStage.COLLECTING)
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    history: Mapped[list] = mapped_column(JSONB, default=list)
    last_asked_field: Mapped[str | None] = mapped_column(String(20))
    turns: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_ai_failures: Mapped[int] = mapped_column(Integer, default=0)
    handover_reason: Mapped[str | None] = mapped_column(String(40))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handed_over_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

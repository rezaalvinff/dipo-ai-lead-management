import uuid
from datetime import datetime

from pydantic import BaseModel, Field, computed_field

from app.schemas.common import ORMModel, to_wib_text


class MessageOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    sender_type: str
    provider: str
    message_type: str
    content: str
    status: str
    provider_message_id: str | None
    error_detail: str | None
    created_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def created_at_wib(self) -> str | None:
        return to_wib_text(self.created_at)


class ConversationOut(ORMModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    lead_id: uuid.UUID | None
    provider: str
    status: str
    handler: str
    assigned_user_id: uuid.UUID | None
    unread_count: int
    last_message_at: datetime | None
    created_at: datetime
    closed_at: datetime | None


class ConversationWithMessages(ConversationOut):
    messages: list[MessageOut] = []


class SendMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class ContactOut(ORMModel):
    id: uuid.UUID
    phone_number: str
    display_name: str | None
    is_simulated: bool
    created_at: datetime


class SimContactCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    phone_number: str | None = Field(
        default=None, description="Opsional. Wajib diawali +62800. Kosongkan untuk otomatis."
    )


class SimSendResponse(BaseModel):
    conversation_id: uuid.UUID
    lead_id: uuid.UUID
    duplicate: bool
    ai_reply_queued: bool
    message: MessageOut | None


class SimStatusRequest(BaseModel):
    status: str = Field(pattern="^(sent|delivered|read|failed)$")


class SimChatOut(BaseModel):
    contact: ContactOut
    conversations: list[ConversationWithMessages]
    state: "QualificationStateOut | None" = None


class SimResetResponse(BaseModel):
    deleted_contacts: int


class HandlerChangeRequest(BaseModel):
    handler: str = Field(pattern="^(ai|admin_queue|sales|admin)$")


class QualificationStateOut(BaseModel):
    conversation_id: uuid.UUID
    handler: str
    lead_id: uuid.UUID | None
    lead_status: str | None
    stage: str
    fields: dict
    last_asked_field: str | None
    handover_reason: str | None
    history: list


class SendTemplateRequest(BaseModel):
    template_name: str = Field(min_length=1, max_length=512, pattern="^[a-z0-9_]+$")
    language_code: str = Field(default="id", min_length=2, max_length=10)
    components: list[dict] = Field(default_factory=list)


class SendMediaRequest(BaseModel):
    media_type: str = Field(pattern="^(image|video|document|audio)$")
    media_id: str = Field(min_length=1, max_length=512)
    caption: str | None = Field(default=None, max_length=1024)
    filename: str | None = Field(default=None, max_length=255)

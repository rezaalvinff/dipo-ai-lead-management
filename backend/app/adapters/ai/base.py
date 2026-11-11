"""Provider-neutral AI agent contract.

The AI only PROPOSES (extracted values + a draft reply). The backend
(QualificationService) validates everything and makes every decision.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field

FieldName = Literal["name", "domicile", "vehicle"]


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "contact" | "assistant"
    text: str


@dataclass(frozen=True)
class KnowledgeContext:
    """Approved knowledge given to the AI, already filtered by the backend."""

    vehicle_models: list[str] = field(default_factory=list)
    vehicle_catalog: dict[str, list[str]] = field(default_factory=dict)  # name -> aliases
    text: str = ""  # rendered block placed in the prompt
    categories_available: set[str] = field(default_factory=set)
    entries: list[tuple[str, str, str]] = field(default_factory=list)  # (category, title, content)


@dataclass(frozen=True)
class AgentRequest:
    history: list[ChatTurn]
    known: dict[str, str | None]  # current backend-validated values
    field_status: dict[str, str]  # missing | collected | declined
    missing_fields: list[str]  # ordered, still askable
    last_asked_field: str | None
    is_first_reply: bool
    knowledge: KnowledgeContext
    city_catalog: dict[str, list[str]] = field(default_factory=dict)
    dealer_name: str = "Mitsubishi DIPO"


class AgentOutput(BaseModel):
    """Structured output every provider must return. Empty string = unknown."""

    customer_name: str = Field(
        description="Nama customer terbaru yang diketahui dari percakapan, atau string kosong."
    )
    domicile: str = Field(
        description="Kota/kabupaten domisili terbaru yang disebut customer, atau string kosong."
    )
    vehicle_model: str = Field(
        description="Model Mitsubishi terbaru yang diminati customer, atau string kosong."
    )
    declined_fields: list[FieldName] = Field(
        description="Data yang customer tolak berikan secara eksplisit."
    )
    intent: Literal["provide_info", "question", "greeting", "request_human", "complaint", "other"]
    asked_field: Literal["name", "domicile", "vehicle", "none"] = Field(
        description="Data yang ditanyakan di akhir balasan."
    )
    reply: str = Field(description="Balasan WhatsApp untuk customer, Bahasa Indonesia.")


@dataclass
class AIResult:
    output: AgentOutput
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class AIProviderError(RuntimeError):
    """Any failure (network, refusal, invalid output). The backend falls back safely."""

    def __init__(self, message: str, *, status: str = "error"):
        super().__init__(message)
        self.status = status  # error | refusal


class AIProvider(Protocol):
    name: str
    model: str

    async def run_turn(self, request: AgentRequest) -> AIResult: ...

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

STATUS_PATTERN = "^(draft|approved|archived)$"
CATEGORY_PATTERN = "^(spec|price|promo|dp|installment|faq|dealer|policy)$"


class ApprovalOut(ORMModel):
    status: str
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---- vehicle models ----
class VehicleModelBase(BaseModel):
    category: str = Field(default="passenger", max_length=50)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    description: str | None = Field(default=None, max_length=4000)
    sort_order: int = 100
    is_active: bool = True

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, v: list[str]) -> list[str]:
        return sorted({a.strip().lower() for a in v if a.strip()})


class VehicleModelCreate(VehicleModelBase):
    name: str = Field(min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern=STATUS_PATTERN)


class VehicleModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=50)
    aliases: list[str] | None = None
    description: str | None = Field(default=None, max_length=4000)
    sort_order: int | None = None
    is_active: bool | None = None
    status: str | None = Field(default=None, pattern=STATUS_PATTERN)


class VehicleModelOut(ApprovalOut):
    id: uuid.UUID
    name: str
    category: str
    aliases: list[str]
    description: str | None
    sort_order: int
    is_active: bool


# ---- variants ----
class VariantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    transmission: str | None = Field(default=None, max_length=30)
    fuel_type: str | None = Field(default=None, max_length=30)
    specs: dict[str, Any] = Field(default_factory=dict)
    price_otr: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=0)
    price_note: str | None = Field(default=None, max_length=200)
    sort_order: int = 100
    is_active: bool = True
    status: str | None = Field(default=None, pattern=STATUS_PATTERN)


class VariantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    transmission: str | None = None
    fuel_type: str | None = None
    specs: dict[str, Any] | None = None
    price_otr: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=0)
    price_note: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    status: str | None = Field(default=None, pattern=STATUS_PATTERN)


class VariantOut(ApprovalOut):
    id: uuid.UUID
    vehicle_model_id: uuid.UUID
    name: str
    transmission: str | None
    fuel_type: str | None
    specs: dict[str, Any]
    price_otr: Decimal | None
    price_note: str | None
    sort_order: int
    is_active: bool


# ---- articles ----
class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(pattern=CATEGORY_PATTERN)
    content: str = Field(min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list)
    vehicle_model_id: uuid.UUID | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = True
    status: str | None = Field(default=None, pattern=STATUS_PATTERN)


class ArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, pattern=CATEGORY_PATTERN)
    content: str | None = Field(default=None, min_length=1, max_length=8000)
    tags: list[str] | None = None
    vehicle_model_id: uuid.UUID | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None
    status: str | None = Field(default=None, pattern=STATUS_PATTERN)


class ArticleOut(ApprovalOut):
    id: uuid.UUID
    title: str
    category: str
    content: str
    tags: list[str]
    vehicle_model_id: uuid.UUID | None
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool


class KnowledgePreview(BaseModel):
    """Exactly what the AI would see right now."""

    vehicle_models: list[str]
    text: str


# ---- settings ----
class SettingOut(BaseModel):
    key: str
    value: Any
    default: Any
    description: str
    is_default: bool


class SettingUpdate(BaseModel):
    value: Any
